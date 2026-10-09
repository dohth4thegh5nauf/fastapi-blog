"""Configurable frontmatter schema for markdown documents.

A `FrontmatterSchema` describes which fields a markdown document may have,
their types, defaults and external names (aliases). It can be built in code
or loaded from a YAML/JSON file, and it produces a Pydantic model on demand.

Fields can also be bound to semantic roles (`title`, `date`, `published`,
`tags`, `description`). The blog uses roles to find the right field without
hardcoding its name, so a document can use `pubDate` instead of `date`.
"""

import copy
import dataclasses
import datetime
import pathlib
from collections.abc import Callable, Mapping
from typing import TYPE_CHECKING, Annotated, Any, Self

import yaml


if TYPE_CHECKING:
    from pydantic import BaseModel


# Semantic roles the blog understands. Each role can be bound to one field.
ROLES: tuple[str, ...] = ("title", "date", "published", "tags", "description")

# Keys the blog sets on every post itself, so a field can't use them as a name.
RESERVED_NAMES: tuple[str, ...] = ("slug", "content")

# How unknown frontmatter keys are handled (same names as in Pydantic).
EXTRA_MODES: tuple[str, ...] = ("forbid", "allow", "ignore")

# Supported field types and their Python annotations.
_TYPES: dict[str, Any] = {
    "str": str,
    "int": int,
    "float": float,
    "bool": bool,
    "datetime": datetime.datetime,
    "date": datetime.date,
    "list[str]": list[str],
    "list[int]": list[int],
    "dict": dict[str, Any],
    "any": Any,
}

# Types that may carry `min_length` / `max_length` constraints.
_LENGTH_TYPES: tuple[str, ...] = ("str", "list[str]", "list[int]")

# Types whose empty value is a container (a missing/null value becomes empty).
_CONTAINER_TYPES: tuple[str, ...] = ("list[str]", "list[int]", "dict")

# Allowed field types for each role.
_ROLE_TYPES: dict[str, tuple[str, ...]] = {
    "title": ("str",),
    "date": ("str", "date", "datetime"),
    "published": ("bool",),
    "tags": ("list[str]",),
    "description": ("str",),
}


class _Missing:
    """Sentinel that means no default value was given."""

    def __repr__(self) -> str:
        return "MISSING"


MISSING: Any = _Missing()


@dataclasses.dataclass(frozen=True)
class FieldSpec:
    """Description of a single frontmatter field.

    Attributes:
        name: Internal field name (a Python identifier).
        type: One of the supported type names, e.g. `str`, `bool`, `list[str]`.
        required: Whether the field must be present in the document.
        default: Value used when the field is absent (not for required fields).
        alias: External key used in the markdown file, if it differs from `name`.
        role: Semantic role the blog uses to find this field (see `ROLES`).
        min_length: Minimum length for `str` and list fields.
        max_length: Maximum length for `str` and list fields.
        description: Human-readable description of the field.

    """

    name: str
    type: str = "str"
    required: bool = False
    default: Any = MISSING
    alias: str | None = None
    role: str | None = None
    min_length: int | None = None
    max_length: int | None = None
    description: str | None = None

    def __post_init__(self) -> None:
        if not self.name.isidentifier() or self.name.startswith(("_", "model_")):
            raise ValueError(
                f"Invalid field name {self.name!r}: use a Python identifier that "
                "does not start with `_` or `model_` (set `alias` for the real key)"
            )
        if self.name in RESERVED_NAMES:
            raise ValueError(
                f"Field name {self.name!r} is reserved by the blog: use another "
                f"name and set `alias={self.name!r}` to keep the key"
            )
        if self.type not in _TYPES:
            raise ValueError(
                f"Unknown type {self.type!r} for field {self.name!r}. "
                f"Supported types: {', '.join(_TYPES)}"
            )
        if self.alias is not None and not self.alias:
            raise ValueError(f"Empty alias for field {self.name!r}")
        if self.required and self.default is not MISSING:
            raise ValueError(f"Required field {self.name!r} cannot have a default")
        if self.role is not None:
            if self.role not in ROLES:
                raise ValueError(
                    f"Unknown role {self.role!r} for field {self.name!r}. "
                    f"Supported roles: {', '.join(ROLES)}"
                )
            if self.type not in _ROLE_TYPES[self.role]:
                raise ValueError(
                    f"Field {self.name!r} has role {self.role!r}, which needs type "
                    f"{' or '.join(_ROLE_TYPES[self.role])}, got {self.type!r}"
                )
        has_length = self.min_length is not None or self.max_length is not None
        if has_length and self.type not in _LENGTH_TYPES:
            raise ValueError(
                f"`min_length`/`max_length` are not supported for type "
                f"{self.type!r} (field {self.name!r})"
            )

    @property
    def key(self) -> str:
        """Return the key used in the markdown file (alias or name)."""
        return self.alias or self.name

    def to_dict(self) -> dict[str, Any]:
        """Return non-default options as a plain dict (without the name)."""
        result: dict[str, Any] = {}
        for item in dataclasses.fields(self):
            if item.name == "name":
                continue
            value = getattr(self, item.name)
            if value == item.default:
                continue
            result[item.name] = value
        return result


@dataclasses.dataclass(eq=False)
class FrontmatterSchema:
    """Set of frontmatter fields plus the policy for unknown keys.

    Attributes:
        fields: Field descriptions.
        extra: What to do with keys not listed in `fields`: `forbid` (error),
            `allow` (keep them) or `ignore` (drop them).

    Example:
        ```python
        schema = FrontmatterSchema(
            fields=(
                FieldSpec("title", required=True, role="title"),
                FieldSpec("pub_date", alias="pubDate", required=True, role="date"),
                FieldSpec("draft", type="bool", default=True),
            ),
            extra="allow",
        )
        Model = schema.model()
        ```

    """

    fields: tuple[FieldSpec, ...] = ()
    extra: str = "forbid"
    _model: Any = dataclasses.field(default=None, init=False, repr=False)
    _payload_model: Any = dataclasses.field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        self.fields = tuple(self.fields)
        if self.extra not in EXTRA_MODES:
            raise ValueError(
                f"Unknown extra mode {self.extra!r}. "
                f"Supported modes: {', '.join(EXTRA_MODES)}"
            )

        # Names and aliases share one namespace, so a document key is never
        # ambiguous.
        seen: dict[str, str] = {}
        for spec in self.fields:
            for token in {spec.name, spec.key}:
                if token in seen:
                    raise ValueError(
                        f"Key {token!r} of field {spec.name!r} clashes with "
                        f"field {seen[token]!r}"
                    )
                seen[token] = spec.name

        roles: dict[str, str] = {}
        for spec in self.fields:
            if spec.role is None:
                continue
            if spec.role in roles:
                raise ValueError(
                    f"Role {spec.role!r} is bound to both {roles[spec.role]!r} "
                    f"and {spec.name!r}"
                )
            roles[spec.role] = spec.name

        # The blog exposes a role under its own name (`post["date"]`), so no other
        # field may already use that name.
        names = {spec.name for spec in self.fields}
        for role, name in roles.items():
            if role != name and role in names:
                raise ValueError(
                    f"Field {role!r} clashes with the role {role!r}, which is "
                    f"bound to field {name!r}: rename it or set `alias`"
                )

    def role_map(self) -> dict[str, str]:
        """Return a mapping from each bound role to its field name."""
        return {spec.role: spec.name for spec in self.fields if spec.role}

    def get(self, name: str) -> FieldSpec | None:
        """Return the field with the given internal name, if any."""
        for spec in self.fields:
            if spec.name == name:
                return spec
        return None

    def field_for_role(self, role: str) -> FieldSpec | None:
        """Return the field bound to the given role, if any."""
        for spec in self.fields:
            if spec.role == role:
                return spec
        return None

    def name_for_role(self, role: str) -> str | None:
        """Return the internal name of the field bound to the given role."""
        spec = self.field_for_role(role)
        if spec is None:
            return None
        return spec.name

    def with_extra(self, extra: str) -> "FrontmatterSchema":
        """Return a copy of the schema with another `extra` mode."""
        return FrontmatterSchema(fields=self.fields, extra=extra)

    def model(self) -> "type[BaseModel]":
        """Return the Pydantic model for this schema (built once, then cached)."""
        if self._model is None:
            self._model = _build_model(self)
        return self._model

    def payload_model(self) -> "type[BaseModel]":
        """Return the REST API request model: `frontmatter` plus `content`.

        It is built once and cached, like `model()`.
        """
        if self._payload_model is None:
            self._payload_model = _build_payload_model(self)
        return self._payload_model

    def dump(
        self,
        instance: "BaseModel",
        *,
        by_alias: bool = False,
        exclude_none: bool = True,
    ) -> dict[str, Any]:
        """Convert a validated model instance to a plain dict.

        Args:
            instance: Instance of the model returned by `model()`.
            by_alias: Use external keys (aliases) instead of internal names.
            exclude_none: Drop fields whose value is `None`.

        Returns:
            Dict with the frontmatter values.

        """
        return instance.model_dump(by_alias=by_alias, exclude_none=exclude_none)

    def to_dict(self) -> dict[str, Any]:
        """Return the schema as a plain dict (the format `from_dict` reads)."""
        return {
            "extra": self.extra,
            "fields": {spec.name: spec.to_dict() for spec in self.fields},
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Self:
        """Build a schema from a plain dict.

        The dict has an optional `extra` key and a `fields` key. `fields` is
        either a mapping `{name: options}` or a list of `{name: ..., ...}`.

        Args:
            data: Schema description, e.g. loaded from YAML or JSON.

        Returns:
            The schema.

        Raises:
            ValueError: If the description is malformed.

        """
        if not isinstance(data, Mapping):
            raise ValueError("Schema description must be a mapping")
        data = dict(data)
        raw_fields = data.pop("fields", None) or {}
        extra = data.pop("extra", "forbid")
        if data:
            raise ValueError(f"Unknown schema key(s): {sorted(data)}")

        specs: list[FieldSpec] = []
        if isinstance(raw_fields, Mapping):
            for name, options in raw_fields.items():
                specs.append(_parse_field(str(name), options))
        elif isinstance(raw_fields, list):
            for item in raw_fields:
                if not isinstance(item, Mapping) or "name" not in item:
                    raise ValueError("Each item in `fields` needs a `name`")
                options = {k: v for k, v in item.items() if k != "name"}
                specs.append(_parse_field(str(item["name"]), options))
        else:
            raise ValueError("`fields` must be a mapping or a list")
        return cls(fields=tuple(specs), extra=extra)

    @classmethod
    def from_file(cls, path: str | pathlib.Path) -> Self:
        """Load a schema from a YAML or JSON file (JSON is valid YAML)."""
        raw = pathlib.Path(path).read_text(encoding="utf-8")
        return cls.from_dict(yaml.safe_load(raw))


def _parse_field(name: str, options: Mapping[str, Any] | None) -> FieldSpec:
    if options is None:
        options = {}
    if not isinstance(options, Mapping):
        raise ValueError(f"Options of field {name!r} must be a mapping")
    known = {item.name for item in dataclasses.fields(FieldSpec)} - {"name"}
    unknown = set(options) - known
    if unknown:
        raise ValueError(f"Unknown option(s) {sorted(unknown)} for field {name!r}")
    return FieldSpec(name=name, **options)


def _implicit_default(spec: FieldSpec) -> Any:
    """Return the default used when a non-required field has none set."""
    if spec.default is not MISSING:
        return spec.default
    if spec.type == "bool":
        return False
    if spec.type == "dict":
        return {}
    if spec.type in _CONTAINER_TYPES:
        return []
    return None


def _make_factory(value: Any) -> Callable[[], Any]:
    # A fresh copy per document, so mutable defaults are never shared.
    def factory() -> Any:
        return copy.deepcopy(value)

    return factory


def _none_to_default(factory: Callable[[], Any]) -> Callable[[Any], Any]:
    # `tags:` with no value is parsed by YAML as `None`; treat it as "empty".
    def convert(value: Any) -> Any:
        if value is None:
            return factory()
        return value

    return convert


def _build_model(schema: FrontmatterSchema) -> "type[BaseModel]":
    from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, create_model

    reserved = set(dir(BaseModel))
    definitions: dict[str, Any] = {}
    for spec in schema.fields:
        if spec.name in reserved:
            raise ValueError(
                f"Field name {spec.name!r} clashes with a Pydantic attribute; "
                "choose another name and set `alias` to the real key"
            )

        annotation: Any = _TYPES[spec.type]
        options: dict[str, Any] = {}
        if spec.alias:
            options["alias"] = spec.alias
        if spec.min_length is not None:
            options["min_length"] = spec.min_length
        if spec.max_length is not None:
            options["max_length"] = spec.max_length
        if spec.description:
            options["description"] = spec.description

        if spec.required:
            info = Field(..., **options)
        else:
            value = _implicit_default(spec)
            factory = _make_factory(value)
            if value is None:
                annotation = annotation | None
            if spec.type in _CONTAINER_TYPES:
                annotation = Annotated[  # type: ignore[valid-type]
                    annotation, BeforeValidator(_none_to_default(factory))
                ]
            info = Field(default_factory=factory, **options)
        definitions[spec.name] = (annotation, info)

    # `extra` is validated in `FrontmatterSchema`, so the `str` is a valid literal.
    config = ConfigDict(
        extra=schema.extra,  # type: ignore[typeddict-item]
        populate_by_name=True,
    )
    return create_model("Frontmatter", __config__=config, **definitions)


def _build_payload_model(schema: FrontmatterSchema) -> "type[BaseModel]":
    from pydantic import ConfigDict, Field, create_model

    return create_model(
        "PostPayload",
        __config__=ConfigDict(extra="forbid"),
        frontmatter=(schema.model(), ...),
        content=(str, Field(..., min_length=1)),
    )


# The schema that matches the original hardcoded behavior.
DEFAULT_SCHEMA = FrontmatterSchema(
    fields=(
        FieldSpec("title", required=True, min_length=1, max_length=200, role="title"),
        FieldSpec("date", required=True, min_length=1, role="date"),
        FieldSpec("published", type="bool", default=False, role="published"),
        FieldSpec("tags", type="list[str]", role="tags"),
        FieldSpec("description", role="description"),
    ),
    extra="forbid",
)

# Same fields, but unknown keys are kept (the old `strict_frontmatter=False`).
LOOSE_DEFAULT_SCHEMA = DEFAULT_SCHEMA.with_extra("allow")

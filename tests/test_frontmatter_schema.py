"""Tests for the configurable frontmatter schema."""

import json

import pytest
from pydantic import ValidationError

from fastapi_blog.models import (
    DEFAULT_SCHEMA,
    LOOSE_DEFAULT_SCHEMA,
    FieldSpec,
    FrontmatterSchema,
    StrictFrontmatter,
    frontmatter_model,
)


# --- FieldSpec validation ---------------------------------------------------


@pytest.mark.parametrize("name", ["", "my-field", "1abc", "_private", "model_x"])
def test_field_spec_rejects_bad_names(name):
    with pytest.raises(ValueError, match="Invalid field name"):
        FieldSpec(name)


def test_field_spec_rejects_unknown_type():
    with pytest.raises(ValueError, match="Unknown type"):
        FieldSpec("x", type="uuid")


def test_field_spec_rejects_unknown_role():
    with pytest.raises(ValueError, match="Unknown role"):
        FieldSpec("x", role="author")


def test_field_spec_rejects_role_with_wrong_type():
    with pytest.raises(ValueError, match="needs type"):
        FieldSpec("flag", type="str", role="published")


def test_field_spec_rejects_required_with_default():
    with pytest.raises(ValueError, match="cannot have a default"):
        FieldSpec("x", required=True, default="a")


def test_field_spec_rejects_length_on_bool():
    with pytest.raises(ValueError, match="min_length"):
        FieldSpec("x", type="bool", max_length=3)


def test_field_spec_key_prefers_alias():
    assert FieldSpec("pub_date", alias="pubDate").key == "pubDate"
    assert FieldSpec("title").key == "title"


# --- FrontmatterSchema validation -------------------------------------------


def test_schema_rejects_unknown_extra_mode():
    with pytest.raises(ValueError, match="Unknown extra mode"):
        FrontmatterSchema(extra="maybe")


def test_schema_rejects_duplicate_names():
    with pytest.raises(ValueError, match="clashes"):
        FrontmatterSchema(fields=(FieldSpec("a"), FieldSpec("a")))


def test_schema_rejects_alias_clashing_with_other_name():
    with pytest.raises(ValueError, match="clashes"):
        FrontmatterSchema(fields=(FieldSpec("a"), FieldSpec("b", alias="a")))


def test_schema_rejects_role_bound_twice():
    with pytest.raises(ValueError, match="bound to both"):
        FrontmatterSchema(
            fields=(FieldSpec("a", role="title"), FieldSpec("b", role="title"))
        )


def test_schema_role_lookup():
    schema = FrontmatterSchema(
        fields=(FieldSpec("pub_date", alias="pubDate", role="date"),)
    )
    assert schema.name_for_role("date") == "pub_date"
    assert schema.name_for_role("tags") is None
    assert schema.field_for_role("date").key == "pubDate"
    assert schema.get("pub_date") is not None
    assert schema.get("missing") is None


# --- Loading from dict / file -----------------------------------------------


def test_from_dict_mapping_form():
    schema = FrontmatterSchema.from_dict(
        {
            "extra": "allow",
            "fields": {
                "title": {"required": True, "role": "title"},
                "draft": {"type": "bool", "default": True},
                "slug": None,
            },
        }
    )
    assert schema.extra == "allow"
    assert [f.name for f in schema.fields] == ["title", "draft", "slug"]
    assert schema.get("draft").default is True


def test_from_dict_list_form():
    schema = FrontmatterSchema.from_dict(
        {"fields": [{"name": "title", "required": True}, {"name": "tags"}]}
    )
    assert [f.name for f in schema.fields] == ["title", "tags"]


@pytest.mark.parametrize(
    "data",
    [
        {"unknown": 1},
        {"fields": {"x": {"typo": 1}}},
        {"fields": [{"required": True}]},
        {"fields": "title"},
        {"fields": {"x": "str"}},
    ],
)
def test_from_dict_rejects_malformed_input(data):
    with pytest.raises(ValueError):
        FrontmatterSchema.from_dict(data)


def test_from_file_yaml_and_json(tmp_path):
    description = {
        "extra": "ignore",
        "fields": {"title": {"required": True}, "n": {"type": "int", "default": 0}},
    }
    yaml_file = tmp_path / "schema.yaml"
    yaml_file.write_text(
        "extra: ignore\nfields:\n  title: {required: true}\n  n: {type: int, default: 0}\n"
    )
    json_file = tmp_path / "schema.json"
    json_file.write_text(json.dumps(description))

    for path in (yaml_file, json_file):
        schema = FrontmatterSchema.from_file(path)
        assert schema.extra == "ignore"
        assert schema.get("n").default == 0


def test_to_dict_round_trip():
    schema = FrontmatterSchema.from_dict(DEFAULT_SCHEMA.to_dict())
    assert schema.to_dict() == DEFAULT_SCHEMA.to_dict()


# --- Generated Pydantic model -----------------------------------------------


def test_model_is_cached():
    assert DEFAULT_SCHEMA.model() is DEFAULT_SCHEMA.model()


def test_default_schema_matches_strict_frontmatter():
    """The default schema must behave exactly like the old hardcoded model."""
    valid = [
        {"title": "T", "date": "2024-01-01"},
        {"title": "T", "date": "2024-01-01", "published": True, "tags": ["a"]},
        {"title": "T", "date": "2024-01-01", "tags": None, "description": "d"},
    ]
    for data in valid:
        old = StrictFrontmatter(**data).model_dump()
        new = DEFAULT_SCHEMA.model()(**data).model_dump()
        assert new == old

    invalid = [
        {},
        {"title": "", "date": "2024-01-01"},
        {"title": "x" * 201, "date": "2024-01-01"},
        {"title": "T"},
        {"title": "T", "date": ""},
        {"title": "T", "date": "2024-01-01", "unknown": 1},
        {"title": "T", "date": "2024-01-01", "published": "maybe"},
    ]
    for data in invalid:
        with pytest.raises(ValidationError):
            StrictFrontmatter(**data)
        with pytest.raises(ValidationError):
            DEFAULT_SCHEMA.model()(**data)


def test_loose_default_schema_keeps_unknown_keys():
    model = LOOSE_DEFAULT_SCHEMA.model()(title="T", date="d", custom=1)
    assert model.model_dump()["custom"] == 1


def test_extra_ignore_drops_unknown_keys():
    schema = FrontmatterSchema(fields=(FieldSpec("title"),), extra="ignore")
    assert schema.model()(title="T", other=1).model_dump() == {"title": "T"}


def test_alias_accepted_by_key_and_by_name():
    schema = FrontmatterSchema(
        fields=(FieldSpec("pub_date", alias="pubDate", required=True),)
    )
    model = schema.model()
    by_alias = model(**{"pubDate": "2024-01-01"})
    by_name = model(pub_date="2024-01-01")
    assert by_alias.pub_date == by_name.pub_date == "2024-01-01"
    assert schema.dump(by_alias) == {"pub_date": "2024-01-01"}
    assert schema.dump(by_alias, by_alias=True) == {"pubDate": "2024-01-01"}


def test_custom_types_and_defaults():
    schema = FrontmatterSchema(
        fields=(
            FieldSpec("count", type="int", default=3),
            FieldSpec("draft", type="bool", default=True),
            FieldSpec("meta", type="dict"),
            FieldSpec("ratings", type="list[int]"),
            FieldSpec("note"),
        )
    )
    values = schema.model()().model_dump()
    assert values == {
        "count": 3,
        "draft": True,
        "meta": {},
        "ratings": [],
        "note": None,
    }


def test_null_container_becomes_empty():
    schema = FrontmatterSchema(fields=(FieldSpec("tags", type="list[str]"),))
    assert schema.model()(tags=None).tags == []


def test_mutable_defaults_are_not_shared():
    schema = FrontmatterSchema(fields=(FieldSpec("tags", type="list[str]"),))
    first = schema.model()()
    first.tags.append("x")
    assert schema.model()().tags == []


def test_length_constraints():
    schema = FrontmatterSchema(
        fields=(FieldSpec("code", required=True, min_length=2, max_length=3),)
    )
    model = schema.model()
    assert model(code="abc").code == "abc"
    for bad in ("a", "abcd"):
        with pytest.raises(ValidationError):
            model(code=bad)


def test_field_name_clashing_with_pydantic_attribute():
    schema = FrontmatterSchema(fields=(FieldSpec("json"),))
    with pytest.raises(ValueError, match="clashes with a Pydantic attribute"):
        schema.model()


# --- frontmatter_model integration ------------------------------------------


def test_frontmatter_model_without_schema_is_unchanged():
    assert frontmatter_model(True).__name__ == "StrictFrontmatter"
    assert frontmatter_model(False).__name__ == "LooseFrontmatter"
    assert frontmatter_model().__name__ == "StrictFrontmatter"


def test_frontmatter_model_with_schema():
    schema = FrontmatterSchema(fields=(FieldSpec("title"),))
    assert frontmatter_model(schema=schema) is schema.model()

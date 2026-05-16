import re
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator


SLUG_PATTERN = r"^[a-z0-9][a-z0-9-]{0,99}$"
SLUG_RE = re.compile(SLUG_PATTERN)

Slug = Annotated[str, StringConstraints(pattern=SLUG_PATTERN)]


class StrictFrontmatter(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=200)
    date: str = Field(min_length=1)
    published: bool = False
    tags: list[str] = Field(default_factory=list)
    description: str | None = None

    @field_validator("tags", mode="before")
    @classmethod
    def _coerce_none_to_empty(cls, value: Any) -> Any:
        return [] if value is None else value


class LooseFrontmatter(StrictFrontmatter):
    model_config = ConfigDict(extra="allow")


def frontmatter_model(strict: bool) -> type[StrictFrontmatter]:
    return StrictFrontmatter if strict else LooseFrontmatter


class StrictPostPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    frontmatter: StrictFrontmatter
    content: str = Field(min_length=1)


class LoosePostPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    frontmatter: LooseFrontmatter
    content: str = Field(min_length=1)


def payload_model(strict: bool) -> type[StrictPostPayload | LoosePostPayload]:
    return StrictPostPayload if strict else LoosePostPayload


def is_valid_slug(slug: str) -> bool:
    return bool(SLUG_RE.match(slug))


def dump_frontmatter(fm: StrictFrontmatter) -> dict[str, Any]:
    return fm.model_dump(exclude_none=True)

import datetime
import functools
import logging
import pathlib
from typing import Any

import markdown as md  # type: ignore[import-untyped]
import nh3
import yaml
from pydantic import ValidationError
from pymdownx import emoji  # type: ignore

from .models import (
    DEFAULT_SCHEMA,
    LOOSE_DEFAULT_SCHEMA,
    FrontmatterSchema,
    frontmatter_model,
)


logger = logging.getLogger(__name__)


def resolve_schema(
    strict: bool = True, schema: FrontmatterSchema | None = None
) -> FrontmatterSchema:
    """Return the schema in effect: the given one or the built-in default.

    Args:
        strict: Used only when `schema` isn’t given (see `frontmatter_model`).
        schema: Custom frontmatter schema.

    Returns:
        The schema whose roles tell the blog which field means what.

    """
    if schema is not None:
        return schema
    return DEFAULT_SCHEMA if strict else LOOSE_DEFAULT_SCHEMA


def build_post(
    values: dict[str, Any], slug: str, schema: FrontmatterSchema
) -> dict[str, Any]:
    """Build the post dict used by routes and templates.

    The dict has every frontmatter field under its internal name, plus each
    bound role under the role’s own name (for example `post["date"]` is the
    value of the field with the `date` role). Templates only use role names.

    Args:
        values: Validated frontmatter values keyed by internal field name.
        slug: Post slug (the file name without `.md`).
        schema: Frontmatter schema that produced `values`.

    Returns:
        The post dict. `title` falls back to the slug when it’s empty.

    """
    post = dict(values)
    post["slug"] = slug
    for role, name in schema.role_map().items():
        post[role] = values.get(name)
    if not post.get("title"):
        post["title"] = slug
    return post


def _date_sort_key(value: Any) -> str:
    # `datetime` is a subclass of `date`. ISO strings sort like the dates do and
    # stay comparable with plain string dates (and with naive/aware datetimes).
    if isinstance(value, datetime.date):
        return value.isoformat()
    return str(value)


def sort_posts(posts: list[dict[str, Any]], schema: FrontmatterSchema) -> list[dict]:
    """Sort posts: newest first by the `date` role, undated ones last.

    Without a `date` role there is nothing to sort by, so posts are ordered by
    slug. Posts with an empty date come after the dated ones, ordered by slug.

    Args:
        posts: Post dicts made by `build_post`.
        schema: Frontmatter schema in effect.

    Returns:
        A new sorted list.

    """
    if "date" not in schema.role_map():
        return sorted(posts, key=lambda x: x["slug"])
    dated = [x for x in posts if x.get("date") is not None]
    undated = [x for x in posts if x.get("date") is None]
    dated.sort(key=lambda x: _date_sort_key(x["date"]), reverse=True)
    undated.sort(key=lambda x: x["slug"])
    return dated + undated


def _is_published(post: dict[str, Any], schema: FrontmatterSchema) -> bool:
    # Without a `published` role there is no draft concept: all posts are public.
    if "published" not in schema.role_map():
        return True
    return bool(post.get("published"))


@functools.lru_cache(maxsize=128)
def list_posts(
    published: bool = True,
    posts_dirname: str = "posts",
    strict: bool = True,
    schema: FrontmatterSchema | None = None,
) -> tuple[dict, ...]:
    """List posts from markdown files, newest first.

    Args:
        published: Return published posts (`True`) or drafts (`False`).
        posts_dirname: Directory with the markdown files.
        strict: Forbid unknown frontmatter keys. Ignored if `schema` is given.
        schema: Custom frontmatter schema. Its roles decide which field is the
            title, date, published flag, tags and description.

    Returns:
        Tuple of post dicts (see `build_post`). Invalid files are skipped.

    """
    effective = resolve_schema(strict, schema)
    Model = frontmatter_model(strict, schema)
    posts: list[dict] = []
    for post in pathlib.Path(".").glob(f"{posts_dirname}/*.md"):
        try:
            raw = post.read_text().split("---")[1]
        except IndexError:
            logger.warning("Skipping %s: missing YAML frontmatter", post)
            continue

        try:
            data = yaml.safe_load(raw)
        except yaml.YAMLError as exc:
            logger.warning("Skipping %s: invalid YAML (%s)", post, exc)
            continue

        if not isinstance(data, dict):
            logger.warning("Skipping %s: frontmatter is not a mapping", post)
            continue

        try:
            fm = Model(**data)
        except ValidationError as exc:
            logger.warning("Skipping %s: %s", post, exc)
            continue

        posts.append(build_post(fm.model_dump(), post.stem, effective))

    posts = sort_posts(posts, effective)
    return tuple(x for x in posts if _is_published(x, effective) is published)


def load_content_from_markdown_file(
    path: pathlib.Path, sanitize: bool = False
) -> dict[str, str | dict]:
    raw: str = path.read_text()
    metadata = yaml.safe_load(raw.split("---")[1])
    markdown_text = "\n---\n".join(raw.split("---")[2:])
    page: dict[str, str | dict] = {
        "metadata": metadata,
        "markdown": markdown_text,
        "html": markdown(markdown_text, sanitize=sanitize),
    }
    return page


extensions = [
    "markdown.extensions.tables",
    "toc",  # "markdown.extensions.toc
    # "markdown.extensions.toc",
    "pymdownx.magiclink",
    "pymdownx.betterem",
    "pymdownx.tilde",
    "pymdownx.emoji",
    "pymdownx.tasklist",
    "pymdownx.superfences",
    "pymdownx.saneheaders",
]

extension_configs: dict[str, dict[str, Any]] = {
    "markdown.extensions.toc": {
        "permalink": True,
        "permalink_leading": True,
        "title": "Tabula Rasa",
    },
    "pymdownx.magiclink": {
        "repo_url_shortener": True,
        "repo_url_shorthand": True,
        "provider": "github",
        "user": "facelessuser",
        "repo": "pymdown-extensions",
    },
    "pymdownx.tilde": {"subscript": False},
    "pymdownx.emoji": {
        "emoji_index": emoji.gemoji,
        "emoji_generator": emoji.to_png,
        "alt": "short",
        "options": {
            "attributes": {"align": "absmiddle", "height": "20px", "width": "20px"},
            "image_path": "https://github.githubassets.com/images/icons/emoji/unicode/",
            "non_standard_image_path": "https://github.githubassets.com/images/icons/emoji/",
        },
    },
    "toc": {
        "title": "Table of Contents!",  # Title for the table of contents
        "anchorlink": True,  # Add anchor links to the headers
        "permalink": "# ",  # Add permanent links to the headers
        "permalink_leading": True,  # Add permanent links to the headers
    },
}


def markdown(text: str, sanitize: bool = False) -> str:
    html = md.markdown(text, extensions=extensions, extension_configs=extension_configs)
    if sanitize:
        html = nh3.clean(html)
    return html

import functools
import logging
import pathlib
from typing import Any

import markdown as md  # type: ignore[import-untyped]
import nh3
import yaml
from pydantic import ValidationError
from pymdownx import emoji  # type: ignore

from .models import frontmatter_model


logger = logging.getLogger(__name__)


@functools.lru_cache(maxsize=128)
def list_posts(
    published: bool = True,
    posts_dirname: str = "posts",
    strict: bool = True,
) -> tuple[dict, ...]:
    Model = frontmatter_model(strict)
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

        post_dict = fm.model_dump()
        post_dict["slug"] = post.stem
        posts.append(post_dict)

    posts.sort(key=lambda x: x["date"], reverse=True)
    return tuple(x for x in posts if x["published"] is published)


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

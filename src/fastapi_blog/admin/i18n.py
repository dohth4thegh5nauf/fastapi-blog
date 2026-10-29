"""Backward-compatible alias of `fastapi_blog.i18n`.

The translation helpers moved to `fastapi_blog.i18n` because the public blog
uses them too, and the blog must work without the `admin` extra.
"""

from ..i18n import (  # noqa: F401
  TranslationSection,
  Translator,
  get_all_locale_names,
  get_locale_name,
  load_translations,
)

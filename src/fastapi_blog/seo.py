"""SEO frontmatter fields (TODO 5.9.1) and site-wide settings (TODO 5.9.2).

`seo_fields()` returns a `FieldSpec` per SEO role (see `models/schema.py`'s
`ROLES`/`_ROLE_TYPES`), with the `choices`/`label`/`hint` TODO 5.9.1
describes. A schema author adds the whole set or a subset, and may rename
or re-alias any of them — the returned `FieldSpec`s use the role name as
the field name, nothing more.

`SeoConfig` (in `models/schema.py`) holds the site-wide settings: the
`seo:` section of a schema file or the `seo=` argument of
`add_blog_to_fastapi()`/`setup_fastapi_blog()`. `resolve_seo_config()` picks
the effective one. The substitution order (5.9.3) and the full
`<head>`/social-tag output (5.9.4) aren't built yet, so most of these roles
and settings still have no visible effect on a rendered page (only
`site_name` reaches the page header).
"""

from typing import Any

from .models import ROBOTS_DIRECTIVES, FieldSpec, FrontmatterSchema, SeoConfig


# One FieldSpec per SEO role, keyed by role name (also the field's default
# name — `seo_fields()` returns them in this order).
_FIELDS: dict[str, FieldSpec] = {
  'seo_title': FieldSpec(
    'seo_title',
    role='seo_title',
    label='SEO title',
    hint='Title for <title>/og:title/twitter:title; falls back to the title.',
  ),
  'canonical': FieldSpec(
    'canonical',
    role='canonical',
    label='Canonical URL',
    hint=(
      'Absolute https:// URL or a path from the site root; otherwise the '
      'canonical URL is computed from the request.'
    ),
  ),
  'robots': FieldSpec(
    'robots',
    type='list[str]',
    role='robots',
    choices=ROBOTS_DIRECTIVES,
    label='Robots directives',
    hint='meta robots directives: ' + ', '.join(ROBOTS_DIRECTIVES),
  ),
  'image': FieldSpec(
    'image',
    role='image',
    label='Social image',
    hint='Path within the site, or an absolute URL, for og:image/twitter:image.',
  ),
  'image_alt': FieldSpec(
    'image_alt',
    role='image_alt',
    label='Image alt text',
    hint='og:image:alt/twitter:image:alt; required once `image` is set.',
  ),
  'updated': FieldSpec(
    'updated',
    type='date',
    role='updated',
    label='Updated',
    hint='Last-modified date; falls back to the date.',
  ),
  'author': FieldSpec(
    'author',
    role='author',
    label='Author',
    hint='Falls back to the site default author, if configured.',
  ),
  'lang': FieldSpec(
    'lang',
    role='lang',
    label='Language',
    hint='BCP 47 language code; falls back to the request locale.',
  ),
  'redirect_from': FieldSpec(
    'redirect_from',
    type='list[str]',
    role='redirect_from',
    label='Redirect from',
    hint="This document's previous URLs (slugs or paths).",
  ),
}


def seo_fields(roles: 'tuple[str, ...] | None' = None) -> tuple[FieldSpec, ...]:
  """Return `FieldSpec`s for the SEO roles, ready to add to a schema.

  Args:
      roles: Which SEO roles to include (e.g. `('canonical', 'robots')`).
          `None` (default) returns all of them. `description` isn't
          included — it's an existing role (not SEO-specific), add it
          separately.

  Returns:
      One `FieldSpec` per requested role, named after the role; a schema
      author can still rename or re-alias any of them before use.

  Raises:
      ValueError: `roles` names something that isn't an SEO role.

  """
  if roles is None:
    return tuple(_FIELDS.values())
  unknown = set(roles) - set(_FIELDS)
  if unknown:
    raise ValueError(f'Unknown SEO role(s): {sorted(unknown)}')
  return tuple(_FIELDS[role] for role in roles)


def resolve_seo_config(
  seo: SeoConfig | None,
  schema: FrontmatterSchema | None,
) -> SeoConfig | None:
  """Return the effective site-wide SEO settings (TODO 5.9.2).

  The `seo=` argument is stronger than the schema's `seo` section: when it's
  given, it replaces the section as a whole (the two aren't merged key by
  key, so what's in effect is always readable from one place).

  Args:
      seo: The `seo=` argument of `add_blog_to_fastapi()` or
          `setup_fastapi_blog()`, if any.
      schema: The posts schema, whose `seo` section is the fallback.

  Returns:
      The settings, or `None` when there's neither an argument nor a section
      (then only the TODO 5.9.6 fixes apply, per П6).

  """
  if seo is not None:
    return seo
  if schema is not None:
    return schema.seo
  return None


import datetime as _dt
import html.parser as _html_parser
import json as _json
import re as _re
import urllib.parse as _url


def _excerpt(source: str, limit: int) -> str:
  class Text(_html_parser.HTMLParser):
    def __init__(self):
      super().__init__()
      self.parts, self.hidden = [], 0
    def handle_starttag(self, tag, attrs):
      if tag in ('script', 'style'): self.hidden += 1
    def handle_endtag(self, tag):
      if tag in ('script', 'style') and self.hidden: self.hidden -= 1
    def handle_data(self, data):
      if not self.hidden: self.parts.append(data)
  parser = Text()
  parser.feed(source or '')
  value = ' '.join(parser.parts)
  value = _re.sub(r'!?(?:\[[^\]]*\])\([^)]*\)', ' ', value)
  value = _re.sub(r'[`*_>#~]+', ' ', value)
  value = ' '.join(value.split())
  if len(value) <= limit: return value
  value = value[:limit + 1]
  return value.rsplit(' ', 1)[0].rstrip(' ,.;:!?') if ' ' in value else value[:limit]


def _valid_url(value: Any) -> str | None:
  if not isinstance(value, str) or not value: return None
  parts = _url.urlsplit(value)
  if parts.scheme.lower() in ('http', 'https') and parts.netloc: return value
  if value.startswith('/') and not value.startswith('//'): return value
  return None


def _iso(value: Any) -> str | None:
  if isinstance(value, (_dt.date, _dt.datetime)): return value.isoformat()
  return value if isinstance(value, str) and value else None


def build_head(document: dict[str, Any] | None = None, *,
               config: SeoConfig | None = None, request_url: str = '',
               locale: str = 'en', page_type: str = 'article',
               body: str = '') -> dict[str, Any]:
  """Resolve frontmatter SEO roles according to TODO 5.9.3."""
  if config is None: return {}
  doc = document or {}
  title = doc.get('seo_title') or doc.get('title')
  if title and config.title_template:
    title = config.title_template.format(title=title, site_name=config.site_name or '')
  title = title or config.site_name
  description = doc.get('description')
  if not description and page_type in ('index', 'list', 'tags', 'tag', 'page'):
    description = config.index_description
  if not description and config.description_fallback == 'excerpt':
    description = _excerpt(body, config.description_length)
  canonical = _valid_url(doc.get('canonical'))
  base = config.site_url
  if not base and request_url:
    parsed = _url.urlsplit(request_url)
    base = f'{parsed.scheme}://{parsed.netloc}'
  if canonical and canonical.startswith('/'):
    canonical = (base or '') + canonical
  if not canonical and request_url:
    canonical = request_url.split('?', 1)[0]
  image = _valid_url(doc.get('image')) or _valid_url(config.default_image)
  if image and image.startswith('/') and base:
    image = base.rstrip('/') + image
  updated = _iso(doc.get('updated')) or _iso(doc.get('date'))
  author = doc.get('author') or config.default_author
  authors = author if isinstance(author, list) else ([author] if author else [])
  robots = list(dict.fromkeys([*(doc.get('robots') or []), *config.default_robots]))
  language = doc.get('lang') or locale
  tags, published = doc.get('tags') or [], _iso(doc.get('date'))
  structured = None
  if config.structured_data != 'none' and page_type == 'article':
    structured = {
      '@context': 'https://schema.org',
      '@type': 'BlogPosting' if config.structured_data == 'blogposting' else 'Article',
      'headline': title, 'description': description, 'image': image,
      'datePublished': published, 'dateModified': updated,
      'author': [{'@type': 'Person', 'name': x} for x in authors],
      'inLanguage': language, 'mainEntityOfPage': canonical, 'keywords': tags,
    }
    structured = {k: v for k, v in structured.items() if v not in (None, [], '')}
  jsonld = _json.dumps(structured, ensure_ascii=False).replace('&', r'\\u0026').replace('<', r'\\u003c').replace('>', r'\\u003e') if structured else None
  return {
    'title': title, 'description': description, 'canonical_url': canonical,
    'robots': robots, 'author': ', '.join(map(str, authors)) or None,
    'og_enabled': config.og, 'og_type': 'article' if page_type == 'article' else 'website',
    'og_title': title, 'og_description': description, 'og_url': canonical,
    'og_image': image, 'og_image_alt': doc.get('image_alt'),
    'og_site_name': config.site_name, 'og_locale': language,
    'og_published_time': published, 'og_modified_time': updated, 'og_tags': tags,
    'twitter_card': config.twitter_card, 'twitter_title': title,
    'twitter_description': description, 'twitter_image': image,
    'twitter_image_alt': doc.get('image_alt'), 'structured_data_json': jsonld,
    'lang': language,
  }

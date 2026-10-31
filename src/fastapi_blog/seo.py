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

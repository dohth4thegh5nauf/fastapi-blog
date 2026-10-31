# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [0.9.0] - Unreleased

### SEO page metadata: resolver and head output (TODO 5.9.3–5.9.4, partial)

- Added `seo.build_head()` to resolve role-based title, description, canonical,
  image, updated/date, author, robots and language values in the specified
  fallback order. Excerpt fallback strips HTML/Markdown-like syntax and cuts
  at a deterministic word boundary.
- Added the overridable `partials/_seo_head.html` fragment and wired it through
  the `seo_head` block in `layouts/base.html`. When SEO configuration is absent,
  the legacy title, description and canonical output remains in place.
- Added optional Open Graph, Twitter Card and schema.org BlogPosting/Article
  output. JSON-LD embedded in the script element escapes `<`, `>` and `&`.
- Remaining: finish canonical/hreflang response-header integration, broaden
  route-level coverage for pages and listing pages, and implement 5.9.5,
  5.9.7 and 5.9.8.


### Site-wide SEO settings: `SeoConfig` and the `seo:` section (TODO 5.9.2)

- `SeoConfig` (`fastapi_blog.models`) holds the settings from TODO 5.9.2:
  `site_url`, `site_name`, `title_template`, `default_image`,
  `default_author`, `default_robots`, `index_description`, `og`,
  `twitter_card`, `structured_data`, `description_fallback`,
  `description_length`, `noindex_tags`. It's the `seo:` section of a schema
  file (`FrontmatterSchema.seo`, read by `from_dict`/`from_file`, written by
  `to_dict`) and the `seo=` argument of `add_blog_to_fastapi()` and
  `setup_fastapi_blog()`
- The argument is stronger than the section and replaces it as a whole (no
  key-by-key merge); `seo.resolve_seo_config(seo, schema)` is the one place
  that decides. `seo: {}` is a section with all defaults, so the SEO output
  of TODO 5.9.4 will switch on for it; without a section and an argument
  nothing changes (П6)
- Every value is checked when the schema is loaded, and the error names the
  key (`` `seo.twitter_card` must be … ``): `site_url` must be an `http(s)`
  URL without a query or fragment (a trailing `/` is dropped, so absolute
  addresses have one spelling); `default_image` must be an `http(s)` URL or
  a path from the site root (`javascript:`, `data:`, `//host` and relative
  paths are refused); `default_robots` must be a list of the four known
  directives; `title_template` may only use `{title}` and `{site_name}`
  (no positional, attribute, index, conversion or format-spec forms, which
  `str.format` would otherwise let through until TODO 6.4's language
  exists). Unknown keys and a non-mapping section are errors too
- Fixed: the routers of the non-default locales were built without `seo=`,
  so `/ru/blog/...` lost the `site_name` that `/blog/...` had
- Fixed: `FrontmatterSchema.with_extra()` dropped `seo` and
  `published_values` (a schema with a `status` role couldn't even be
  copied; `LOOSE_DEFAULT_SCHEMA` was unaffected only because it has none)
- Still no visible effect beyond `site_name` in the page header: the
  substitution order (5.9.3) and the `<head>` output (5.9.4) consume these
  settings next

### Housekeeping: test invocation, stale references, invariance wiring

- `make test` and both CI workflows called `pytest .`, which overrides
  `testpaths` and crashed collecting the `+/` reference-material directory;
  they now call plain `pytest`, leaving collection scoped to `tests/` per
  `pyproject.toml`
- `Makefile run_admin_roles` advertised credentials that contradict the
  actual `tests/examples/admin_with_roles.py` users (every password there
  is `password`)
- `docs/ROLE_MANAGEMENT.md`, `docs/CODEBASE_ANALYSIS.md` and
  `docs/CODEBASE_SUMMARY_RU.md` still referenced the removed
  `fastapi_blog.admin.models_role` module and otherwise stale file trees;
  updated to the current `admin/models/` layout and real file names
- Added the spec-mandated invariance-test wiring (`tests/test_invariance.py`
  plus `tests/forbidden_names.txt`, the latter intentionally left empty for
  the owner per `TODO.md` section 8) and corrected stale counts/versions in
  `README.md`, `QUICKSTART.md` and the docs footers

### Store error hierarchy

- `store` raises specific errors now, all subclasses of `store.StoreError`:
  `InvalidSlugError` (bad slug or directory escape), `ParseError` (bad YAML
  frontmatter or a non-UTF-8 file, also raised by `read`), `NotFoundError`
  (missing document) and `OperationNotAllowedError` (`create`/`delete`
  forbidden); `ConflictError` joins the hierarchy, still carrying
  `status_code`. Each one also inherits the builtin it replaces
  (`ValueError`, `FileNotFoundError`, `PermissionError`), so every existing
  `except` clause keeps working unchanged

### JSON-LD contexts: local files, allow-listed URLs, limits (TODO 5.5)

- `jsonld.context` accepts a path to a file inside the project root (YAML
  or JSON; a whole document's `@context` is extracted) or an allow-listed
  URL, beside inline mappings and lists — loaded by the new
  `jsonld.resolve_context(schema, project_root=...)`. Nothing in a context
  is executed; a context outside the project root is refused
- Remote contexts need the `jsonld` extra plus an explicit
  `allow_remote_contexts` entry: fetch has a timeout, a `max_context_bytes`
  size limit and refuses redirects to another host. A context that can't
  be loaded raises `ContextUnavailableError` (HTTP routes answer 503,
  `export` exits 64) — never a silent "ok"
- New `jsonld` config limits: `max_context_bytes` and `max_documents`
  (the latter caps an exported `@graph`, enforced by
  `collection_to_jsonld`)
- The emission functions stay pure: callers resolve the context and pass
  it as `context=`; `uncovered_keys(schema, project_root=...)` resolves a
  local context before checking for lost terms

### Frontmatter field types and lost-term control (TODO 5.1, 5.6)

- New field types: `link` and `list[link]` (a string pointing at another
  resource — a slug, a compact IRI or an absolute IRI) with the target
  options `collection`, `value_field` and `[{field, values}]` `filters`;
  `file` and `image` (a path kept as a string) with `media_dir` and
  `public_path`. `pattern` now also applies to `link`/`file`/`image`,
  `item_pattern` to `list[link]`, and `choices` to all of them
- `fastapi_blog.jsonld.uncovered_keys(schema)` reports the schema keys an
  inline `@context` doesn't cover (a same-name term, a `prefix:` term or
  `@vocab`), `content_term` included. URL context items are skipped, not
  loaded — loading files and remote contexts is TODO 5.5

### Document storage: merge-on-rewrite, nested collections, page schema (TODO 4.5, 4.6)

- Rewriting a post through the REST API merges the dump over the file's
  current frontmatter instead of replacing it: known keys keep their
  positions, unknown keys survive when the schema is `extra: 'allow'`, a
  known field emptied to `None` is dropped, and schema fields the file
  didn't have yet are appended in schema order
  (`FrontmatterSchema._merge_for_rewrite`). Admin-panel writes still bypass
  schema validation — that remainder is TODO 7.6 (phase E)
- `Collection(depth=N)` implements nested collections: the slug is the
  relative path without the extension (`a/b/0001-x`), each segment is
  checked against `slug_pattern`, and at most `N` segments are directories;
  `list()` returns relative slugs and skips files that would not validate
- `slug_pattern` may be a string template using `{dirname}` and
  `{filename}` as one-segment placeholders (plain regex tokens such as
  `{m,n}` quantifiers survive the expansion)
- `store.blog_collections()` builds the two standard collections: the
  `posts_dirname`/`pages_dirname` parameters stay the public surface, and
  the REST API, the admin panel and the JSON-LD routes now construct their
  collections in this one place
- Pages validate against a built-in schema with the fields they have always
  had (`helpers.PAGES_SCHEMA`: `title`, `description`, `author`,
  `extra: 'allow'`); a page that doesn't match is still served with its
  raw frontmatter
- The public page route resolves the page slug through `safe_document_path`
  like every other slug-to-path conversion (TODO 4.1)

### SEO roles and `fastapi_blog.seo.seo_fields()` (TODO 5.9.1)

Nine new semantic roles, the same mechanism as `title`/`date`/`published`:
`seo_title`, `canonical`, `robots`, `image`, `image_alt`, `updated`,
`author`, `lang`, `redirect_from` (`ROLES`/`_ROLE_TYPES` in
`models/schema.py`; `author` is the first role allowed as either `str` or
`list[str]`). `seo.seo_fields(roles=None)` returns a ready `FieldSpec` per
role (`label`, `hint`, `robots`'s `choices` restricted to the four
directives search engines actually act on —
`noindex`/`nofollow`/`noarchive`/`nosnippet`, per TODO 5.9.0's "only what
search engines use" principle) — a schema author adds the whole set, a
subset (`seo_fields(('canonical', 'robots'))`), and can still rename or
re-alias any of them.

Binding these roles has no visible effect yet — nothing reads them. Not
built: `SeoConfig`/the `seo:` schema section (5.9.2), the fallback/
substitution order (5.9.3), and the actual `<head>`/Open Graph/Twitter/
structured-data output (5.9.4) that would make them do something.

### Fixed existing behavior: real page titles, `lang`, `description`, no fork-author branding (TODO 5.9.6, MUST)

`layouts/base.html`'s `<title>` fallback chain checked a top-level
`metadata` context variable that no route ever actually set (every
template that has one sets `page.metadata` instead), so it always fell
through to its last, hardcoded branch — every single page of every blog
built with this package rendered `<title>Daniel Roy Greenfeld</title>`
(the original fork author's name), regardless of which post or page was
being viewed. `index.html` independently pinned its own `{% set title =
"Daniel Roy Greenfeld" %}` on top of that. Fixed properly rather than just
swapping the fallback text: every route (`blog_index`, `blog_post`,
`blog_posts`, `blog_tags`, `blog_tag`, `blog_page`, the 404 page) now sets
a real `title` (and `description`, where the schema/page has one) in its
own template context, and `layouts/base.html` just prints it — no more
dead `metadata` branch.

Also fixed while in the same file, as the same class of bug (hardcoded
content that isn't universal, П3): `<html>` had no `lang` attribute at
all (now `{{ lang|default(locale, true) }}` — ready for the `lang` role,
TODO 5.9.1, once it exists); the role `description`'s value was parsed but
never rendered as `<meta name="description">`; the header/footer shipped
the original fork author's own photo (via a malformed `<image>` tag — not
even valid HTML — pointing at a file that was never part of this
package), name, and Mastodon/LinkedIn/Twitter links, none of which belong
in a universal package. Replaced with `{{ site_name|default('', true) }}`
(empty for now; wired up for TODO 5.9.2's `SeoConfig.site_name` once that
exists) and removed the social links outright.

Not done from TODO 5.9: the rest is SHOULD/MAY (`seo_title`/`canonical`/
`robots`/etc. roles, `SeoConfig`, Open Graph/Twitter/structured-data
output, sitemap/robots.txt/redirects, `check` findings) — 5.9.6 itself,
the one MUST item that was pure bug-fixing, is what's done here.

### `schema --json-schema` and the `status` role (TODO 5.7)

- `python -m fastapi_blog schema --json-schema` prints the frontmatter's
  JSON Schema (`FrontmatterSchema.model().model_json_schema()`), same
  `--schema`/`--out` as `export`. `choices` and `pattern` weren't visible in
  it before — both are enforced through our own `AfterValidator`s (for a
  named bad value and `re.fullmatch`/custom messages, not Pydantic's
  generic enum/pattern errors), so Pydantic's own schema generation never
  saw them. `_build_model` now also puts them in each field's
  `json_schema_extra` (`enum`/`pattern`), which Pydantic merges into the
  generated schema — the validators are still what actually runs
- New `status` role: a generalization of `published` for schemas with more
  states than draft/published (e.g. draft/review/active/retired).
  `FrontmatterSchema.published_values` (required whenever a field binds
  `status`) says which values count as public; binding `published` and
  `status` on the same schema is now a schema error (they're two answers
  to the same question). `helpers._is_published` checks `status`'s value
  against `published_values` instead of a plain bool when the role is
  bound, so `list_posts(published=...)`, the blog's draft filtering and
  the JSON-LD routes' "published only" rule all pick it up automatically
  — no changes needed in router.py/jsonld.py themselves

### JSON-LD emission: `document_to_jsonld`/`collection_to_jsonld` (TODO 5.2-5.4, partial)

New `fastapi_blog.jsonld` module, built on the existing `alias` mechanism
(a field aliased `'@id'`/`'@type'` supplies that key directly) rather than
anything new in the schema layer itself:

- `FrontmatterSchema` gained a `jsonld: JsonLdConfig | None` field (and
  `from_dict`/`to_dict` support for a schema file's `jsonld:` section, TODO
  5.3): `context`, `base`, `id_template` (a plain `str.format()` template
  with `{base}`/`{collection}`/`{slug}` — not the full slug/template
  language from TODO 6.4, not built yet), `type`, `content_term`
- `document_to_jsonld(frontmatter, *, schema, slug, collection='', content=None)`:
  projects one document — `@context` (when configured), `@id`/`@type`
  (from a field if present, else the config's template/default), then the
  schema's own fields in schema order, by alias. `None`/`''`/`[]`/`{}` are
  omitted; `date`/`datetime` values become ISO 8601 strings; the body is
  only included when `jsonld.content_term` is set
- `collection_to_jsonld(documents, *, schema, collection='', context=None)`:
  `{'@context', '@graph'}` for a whole collection, `@graph` sorted by
  `@id` then slug so two runs produce identical bytes regardless of
  filesystem iteration order (TODO 5.4 criterion 3)

`add_blog_to_fastapi(jsonld_routes=True, ...)` (default `False`) now also adds
the HTTP side of 5.4: `GET {prefix}/{slug}.jsonld` and `GET {prefix}/index.jsonld`,
`Content-Type: application/ld+json`. Both only ever serve published posts —
`{slug}.jsonld` 404s for a draft or missing slug, `index.jsonld`'s `@graph`
simply excludes drafts. (`{prefix}/index.jsonld` is registered before
`{prefix}/{slug}.jsonld`, since Starlette matches path routes in
registration order and `index.jsonld` would otherwise also match the
`{slug}` pattern with `slug='index'` first.)

`python -m fastapi_blog export` (new `fastapi_blog/__main__.py`) is the CLI
side: `--posts-dir`, `--schema` (a YAML/JSON schema file; default: the
built-in fields), `--collection` (used by the schema's `id_template`),
`--format jsonld|expanded|nquads` and `--out FILE` (default: stdout).
`expanded`/`nquads` need the `jsonld` extra (`pyld`) and exit `64` with a
clear message when it isn't installed; `nquads` lines are sorted (RDF
statements have no inherent order), so two runs produce byte-identical
output (TODO 5.4 criterion 3, same as `collection_to_jsonld` itself).
Takes `--posts-dir`/`--schema`/`--collection` directly rather than TODO's
literal `--collection NAME`, which presupposes a project-level registry of
named collections (each with its own directory and schema) that doesn't
exist anywhere in this codebase yet — `Collection`s are built ad hoc per
call everywhere else too.

Not done: loading `context` from a local file (TODO 5.5, needs the `jsonld`
extra), and the "lost term" check (TODO 5.6) — 5.4 itself is now done.

### Configurable frontmatter: `choices`, `pattern`, `min`/`max`, `min_items`/`max_items`, `label`/`hint`/`hidden` (TODO 5.1, partial)

`FieldSpec` gained the simpler options from TODO 5.1's table (the ones that
are pure validation/metadata, not a feature of their own):

- `choices`: allowed values — a scalar, or `{value, label}` where `label` is
  display-only and `value` is what's stored/validated. Valid for `str`,
  `int`, `float`, `list[str]`, `list[int]`; for a list type, every element
  must be allowed. Enforced via a Pydantic `AfterValidator`, so the error
  names the actual bad value(s), not just "not a valid enum member"
- `pattern`: a regex string, or `[regex, message]` for a custom error
  message instead of Pydantic's generic one; the whole value must match
  (`re.fullmatch`). Only for `type='str'`. `item_pattern` is the same thing
  applied to every element of a `list[str]` field instead of the field
  itself
- `min`/`max` (`int`/`float` fields, inclusive bounds) and `min_items`/
  `max_items` (`list[str]`/`list[int]` fields, independent of each other,
  unlike `min_length`/`max_length` which this project's own
  `_LENGTH_TYPES` already lets you set independently too — `min_items`/
  `max_items` exist so a schema author doesn't have to read "length" as
  "list item count" on a list field; a field can't set both
  `min_items`/`max_items` and `min_length`/`max_length`, to avoid the
  ambiguity of two options doing the same thing)
- `label` (→ the Pydantic field's `title`, used by the admin form and JSON
  Schema), `hint` and `hidden` (both carried as `json_schema_extra`, since
  Pydantic has no native equivalent — the admin form/`check` read them from
  there)

All of these are validated at schema-definition time (`FieldSpec.__post_init__`):
wrong type for the option, an empty `choices`, an unparsable regex, or
`min_items`+`min_length` both set on one field all raise immediately when
the schema is built, not when a document is later validated against it.

Not done from 5.1: `type: link`/`object`/`file`/`image` (each a
cross-document or nested-schema feature, substantially bigger than a
validation option) and the `jsonld` schema section (5.2–5.7) itself.

### Document storage: path safety wired in everywhere (TODO 4.4)

`store.safe_document_path` (slug pattern + resolved-path containment check)
existed but wasn't called from any of the five places that turn a slug into
a file path. Wired it into all of them, using the same compiled `SLUG_RE`
(now exported from `fastapi_blog.models`) everywhere instead of each site
re-deriving its own slug check:

- `editor.py`'s `_post_path` (REST API and the deprecated UI routes)
- `router.py`'s public `/posts/{post_id}` route (already indirectly safe via
  the `_list_posts()` whitelist, but now also explicit)
- `admin/markdown_crud.py`'s `MarkdownFileManager.load_post`/`save_post`/
  `delete_post`
- `admin/markdown_model.py`'s `MarkdownPost.get_file_path` (used by
  `exists`, `load_from_file`, `save_to_file`, `delete`); its own ad hoc
  `re.match(r'^[a-z0-9-]+$', ...)` check is gone in favor of this

Added `tests/test_markdown_crud.py` and traversal-slug tests in
`test_markdown_model.py`/`test_router.py` covering all five.

### Document storage: `Collection` and `DocumentStore` (TODO 4.1, 4.6, 4.7)

`store.py` gained the one abstraction every caller that turns a slug into a
file should go through:

- `Collection(name, dir, *, slug_pattern=..., extension='md', depth=0,
  create=True, delete=True)`: a directory of same-shaped documents. `depth >
  0` (nested collections) raises `NotImplementedError` — not built yet, kept
  as an explicit gap rather than a half-working guess. Deliberately does
  *not* carry a `FrontmatterSchema` (unlike the literal signature sketched
  in `TODO.md`): schema validation and `on_create`/`read_only` already live
  in `FrontmatterSchema.dump_for_write` (previous section), which callers
  run before `DocumentStore.write`, keeping the storage layer free of the
  Pydantic layer above it.
- `DocumentStore`: `list`/`read`/`exists`/`write`/`delete` over one
  `Collection`. `read` returns a `DocumentRecord` with an `etag` (sha256 of
  the file's content); `write`/`delete` accept `if_match`, raising
  `ConflictError` (`.status_code` 412 on a stale etag, 409 if the document
  doesn't exist) on mismatch. `create=False`/`delete=False` block those
  operations (an existing document can still be rewritten). Writes are
  serialized by an in-process lock per store instance; no cross-process
  locking, as the TODO explicitly rules out.

Migrated onto it: `admin/markdown_crud.py`'s `MarkdownFileManager`, and
`editor.py`'s REST API (`create_post`/`update_post`/`delete_post`/
`get_raw`/`save_post`), which now also return an `ETag` response header and
accept an `If-Match` request header — `update_post`/`delete_post` translate
a stale etag into a 412, a missing document (when `If-Match` was sent) into
409. `get_api_router()`/`add_editor_to_app()` gained `require_if_match:
bool = False`: when `True`, update/delete need the header or get a 428.

**Two `MarkdownPost` implementations, down to one.** `admin/markdown_model.py`
(a second, independent `MarkdownPost`/file-reading implementation, used only
as `HomeView`'s fallback when no custom schema was given) is deleted.
`HomeView` now always goes through `load_posts_for_home` (which itself goes
through `MarkdownFileManager`/`DocumentStore`), passing `DEFAULT_SCHEMA` when
the caller didn't set one.

**`posts_dirname` now actually reaches the admin panel.** It didn't before:
`setup_fastapi_blog(posts_dirname=...)`/`add_blog_to_fastapi` passed it to
the blog and REST API, but the admin panel read posts via
`markdown_crud.get_posts_directory()` alone — a `POSTS_DIR` environment
variable or a cwd-based guess, completely independent of whatever
`posts_dirname` the blog used. A caller that set `posts_dirname` to anything
other than the default `'posts'` got a blog and an admin panel silently
looking at two different directories. `add_admin_to_app()` and
`HomeView`/`_create_admin_for_locale` now take `posts_dirname` too, and
`setup_fastapi_blog` passes it through to both. `get_posts_directory()`
still falls back to `POSTS_DIR`/a cwd guess when no `posts_dirname` is
given, but using the environment variable now raises `DeprecationWarning`.

Not done: 4.6's nested collections (`depth > 0`, `{dirname}`/`{filename}`
slug template tags — the latter also needs 6.4, not started) and the
`posts_dirname`/`pages_dirname` → two-`Collection` sugar layer. The public
blog/REST API/admin surface still takes `posts_dirname: str` rather than a
`Collection`.

### Document storage: `on_create` and `read_only` fields (TODO 4.5)

`FieldSpec` gained `on_create` (`'today' | 'now' | 'uuid'`, with an optional
`on_create_prefix` for `'uuid'`) and `read_only`. A field with `on_create`
must not also be `required` (it fills a value only when one was left unset,
which a required field can never be); `'today'`/`'now'`/`'uuid'` each need a
matching field type (`date`/`datetime`/`str`).

`FrontmatterSchema.dump_for_write(instance, *, is_create, existing=None)`
applies both at the one place that matters — the moment a document is
written — using `instance.model_fields_set` to tell "left unset" apart from
"explicitly sent": on create, it fills every unset `on_create` field once;
on update, it rejects (`ValueError`) a `read_only` field whose new value
differs from `existing`'s. The REST API (`editor.py`'s `create_post`,
`update_post` and the deprecated `/save` route) now calls it instead of
`schema.dump`, turning that `ValueError` into an HTTP 400.

Not done: the admin panel's own save path (`markdown_crud.py`) doesn't go
through `FrontmatterSchema` validation at all yet (see 4.1/4.6 — unifying
the two `MarkdownPost` implementations on one `DocumentStore`), so these two
options only take effect through the REST API for now. Key-order and
unknown-key preservation on rewrite (the rest of 4.5) needs a merge-into-
existing-dict write path rather than a full Pydantic round-trip, which is
really 4.1's `DocumentStore` territory — deferred there rather than bolted
on here.

### Admin UI: one theme/language switcher everywhere

The dependency upgrade (below) left the admin inconsistent: the built-in
Role/User pages got the stock light theme with no theme or language
switcher, while this project's own pages (dashboard, posts) kept a
hand-rolled dark theme with their own switcher that didn't reach the stock
pages at all.

- `admin/templates/layout.html` (new): shadows the bare `"layout.html"` name
  that every page — both `@starlette-admin/list.html`/`detail.html`/
  `edit.html`/`create.html` and this project's own `home.html`/
  `markdown_list.html`/`markdown_edit.html` — extends (directly or
  transitively). Adds the theme toggle and language switcher once, through
  the framework's own `navbar_extra` extension point (see
  `@starlette-admin/templates/layout.html`), instead of duplicating
  DOM-injection JS per page. Removes the old hand-rolled dark-mode CSS
  (hardcoded hex colors) in favor of Tabler's own `data-bs-theme="dark"`
  support, which every page already loads
- Deleted `admin/templates/layouts/base.html` and `layouts/custom_base.html`
  (superseded by `layout.html`), **and the project's `login.html` override
  entirely**: the stock `@starlette-admin/login.html` already extends the
  bare `"layout.html"` name, so it already inherits this project's theme
  through the shadowed `layout.html` — there was nothing left for a custom
  login page to add. `SimpleAuthProvider.render_login` only needed to keep
  passing the project's YAML-based `_` translator through the template
  context. The login page is now the stock Tabler card, matching every
  other page's theme instead of a separately maintained dark-only design
- Fixed two bugs found testing this in a real browser: `render_login` was
  missing the stock "already authenticated → redirect" check (dropped
  during the 1.0 port), so a logged-in user opening `/admin/login` saw the
  form rendered underneath the real navbar, visually overlapping with the
  old login page's own switchers; and the old `login.html`'s logo check
  used `login_logo_url`/`logo_url` as plain values, but 1.0 made both
  callables (`(request) -> str | None`), so the unused-by-default logo
  silently requested a URL that was the Python function's `repr()`
- `MarkdownListView`'s route moved: `/admin/posts/list` → `/admin/posts`
- The top navbar (theme/language/user menu) now stays on screen while the
  page scrolls (`header.navbar { position: sticky; top: 0 }` in
  `layout.html`), matching the sidebar's own fixed position. It used to
  scroll away with the content on every page
- The sidebar no longer reserves a permanent scrollbar gutter: Tabler
  hardcodes `overflow-y: scroll` on it (`.navbar-vertical.navbar-expand-*`),
  which shows a non-functional scrollbar track even though the menu is
  nowhere near tall enough to need one. `layout.html` overrides it to
  `auto`. This was very likely the "header border" artifact reported after
  the first pass at this — the dead scrollbar track sitting right where the
  sidebar meets the navbar, not an actual border
- `pyproject.toml`: added `[tool.pytest.ini_options] testpaths = ["tests"]`.
  Without it, pytest also collected `+/` (reference material per
  `AGENTS.md`, already excluded from ruff/mypy) and failed on its
  cookiecutter template files, which aren't valid Python
- `home.html`/`markdown_list.html`/`markdown_edit.html` each wrapped their
  `{% block content %}` in their own `<div class="container-fluid">`, but
  the shared layout's `.page-body` already wraps `{% block content %}` in
  a `.container-xl` — the extra wrapper double-nested the gutter padding
  and made Home/Posts noticeably narrower than the stock Users/Access
  Control pages. Removed the redundant outer wrapper from all three
  (`markdown_edit.html` keeps its unrelated inner `container-fluid`, used
  for spacing inside the card header, not as a page-level wrapper)
- The sidebar is narrowed from Tabler's default 15rem to 14rem
  (`aside.navbar-vertical.navbar-expand-lg { width: 14rem }` in
  `layout.html`), with the `margin-left` Tabler puts on `.navbar`/
  `.page-wrapper` to make room for it changed to match — the two must move
  together or the content either starts under the sidebar or leaves a gap
  next to it
- Fixed a gap (the width of the scrollbar, e.g. 15px) between the sidebar's
  right edge and the content on every page. Tabler sets `margin-left:
  calc(-100% + 100vw)` on `:root` as a scrollbar-width compensation trick;
  the sidebar is `position: fixed` so it ignores that shift and stays
  flush left, but `.page-wrapper`/`.navbar` are normal flow and get
  shifted on top of their own `margin-left`, opening the gap. `layout.html`
  zeroes that `:root` margin out — nothing else in the project relies on
  the compensation it was doing
- Removing that `:root` margin uncovered a second, pre-existing issue:
  `.container-xl` is centered with `margin: auto` inside `.page-wrapper`,
  so its position depends on the viewport's *content* width, which a page
  tall enough to scroll (e.g. Posts) and a short one with no scrollbar
  (e.g. an empty Users table) disagree on by the scrollbar's own width —
  the container sat a few pixels further right on the short page.
  `layout.html` now reserves the scrollbar's gutter unconditionally
  (`scrollbar-gutter: stable` on `:root`), so every page's content width,
  and therefore its container's position, is identical regardless of
  whether that particular page needs to scroll
- `home.html`'s header block wrapped an `<h2 class="page-title">` in its
  own `.row.g-2` grid, instead of the plain `<h1>` every other page uses
  (both the stock `@starlette-admin/list.html` and this project's own
  `markdown_list.html`/`markdown_edit.html`). That rendered a shorter
  `.page-header`, so Home's content started a few pixels higher than every
  other page's — fixed by matching the same plain-`<h1>` structure
- Fixed a pre-existing, unrelated bug surfaced while fixing the above: the
  header used `{{ t.home }}` for the page title, but the YAML translations
  only define `home.title` (not `home.home`) — the heading and active
  breadcrumb item had silently been rendering empty on every locale
- The theme/language switchers disappeared entirely below the `lg`
  breakpoint (992px): Tabler hides `header.navbar` there (`d-none
  d-lg-flex`), and the sidebar's own mobile header row (shown instead) has
  no hook for our `navbar_extra` content. `layout.html` now forces
  `header.navbar` to stay visible below 992px, while hiding its own
  toggler (targets an always-empty `#navbar-menu` collapse — never
  populated, so hiding it loses nothing) and its own user-menu trigger
  (redundant with the one the sidebar's mobile row already shows), so the
  switchers show up without duplicating anything
- The sidebar's own mobile header row (brand, hamburger, user menu — what's
  visible below 992px once the sidebar itself collapses to an off-canvas
  panel) was pinned to 224px instead of the viewport's full width,
  reported as "the header shrinks in width below 992px". Cause: the 14rem
  sidebar-width override (previous entry) was unscoped, so it also applied
  below 992px — fighting Tabler's own mobile reset, which otherwise turns
  the sidebar into a full-width, in-flow bar there (`position: relative`,
  confirmed live). Scoping the override to `@media (min-width: 992px)`
  (alongside the existing `margin-left: 14rem`, which was already scoped
  the same way) fixes it

### Dependency upgrade

Every dependency floor bumped to its current latest release: `fastapi`
0.116→0.162, `markdown` 3.9→3.11, `nh3` 0.2→0.3, `pydantic` 2.9→2.14,
`pymdown-extensions` 10→12, `uvicorn` 0.35→0.54, `sqlalchemy` 2.0→2.1,
`aiosqlite`/`itsdangerous`/`python-multipart` to latest patch, `pyld` 2→3,
`ruff` 0.13→0.17, `pytest` 8→9, `mypy` 1→2, `coverage`, `setuptools`.
`pyyaml`/`jinja2`/`jinja2-time`/`httpx` were already current.

#### `starlette-admin` 0.16 → 1.0.3 (the one major-breaking bump)

- `auth_provider.py`/`rbac_auth_provider.py`: ported to the new
  `AuthProvider` contract — `is_authenticated`/`get_admin_user` merged into a
  single `authenticate(request) -> AdminUser | None`; `login`/`logout` no
  longer take/return a `Response`; `render_login` keeps our YAML-translated
  login page but matches the new `(request, templates)` signature
- `Admin(...)` now needs an explicit `secret_key` for its own CSRF/flash
  cookies (previously only `SessionMiddleware` needed one); wired through
  from `add_admin_to_app`'s already-validated `secret_key`
- `views.py`/`views_role.py`/`markdown_crud.py`: `CustomView.render()` →
  `@route('') async def index()`; constructor kwargs renamed
  (`label`→`menu_label`, `name`→`route_name`, `template_path` removed);
  `ModelView`/`BaseView` attributes renamed (`label`→`menu_label` for the
  sidebar, `name`→`display_name` for the singular form title,
  `identity`→`key`); `DropDown(label=...)` → `DropDown(menu_label=...)`
- `admin/fields.py` (`MarkdownField`, `TagsField`, `SlugField`): the
  `action` parameter dropped from `serialize_value`/`parse_form_data`; read
  `request.state.action` instead (these classes aren't used by this
  project's own views yet, only exported for consumers)
- **The 4 customized `list.html`/`detail.html`/`edit.html`/`create.html`
  templates (Role/User management pages only) now extend the built-in
  `@starlette-admin/*.html` directly**, instead of our themed
  `layouts/custom_base.html`. 1.0 replaced the DataTables-based rendering
  these were built against with a server-rendered system built from a new
  set of partials/macros; re-theming that wasn't practical to do blind, so
  these 4 pages lost the project's custom dark theme/language switcher (they
  use the stock light theme now) in exchange for actually working — verified
  end-to-end in a real browser: login, create/list/detail/edit a user, role
  list. The blog's own post editor pages (`home.html`, `markdown_list.html`,
  `markdown_edit.html`) are untouched and keep the custom theme
- `passlib[bcrypt]`'s self-test crashes on `bcrypt>=4.1` (`ValueError:
  password cannot be longer than 72 bytes`) — a known passlib/bcrypt
  incompatibility (passlib is unmaintained since 2020). Pinned
  `bcrypt<4.1` in the `admin` extra
- New regression tests: `tests/test_admin_modelview_pages.py` (logs in for
  real, exercises create→list→detail→edit on the Role/User pages — the
  gap that let the empty-table regression through unnoticed); updated
  `tests/test_admin_theme.py` to assert the new extends-stock-template
  design instead of the old custom-theme one

### Phase A: packages, imports, cache

#### Changed
- **Core vs extras.** The core install needs only files: `fastapi`, `jinja2`,
  `jinja2-time`, `markdown`, `nh3`, `pydantic`, `pyyaml`, `pymdown-extensions`,
  `uvicorn`. New extras: `admin` (`starlette-admin[i18n]`, `sqlalchemy[asyncio]`,
  `aiosqlite`, `itsdangerous`, `passlib[bcrypt]`, `python-multipart`) and `jsonld`
  (`pyld`). Install with `pip install "fastapi-blog[admin]"`
- **Lazy admin.** `import fastapi_blog` no longer imports the admin panel.
  `Admin` and `add_admin_to_app` load on first access (PEP 562) and raise an
  `ImportError` that names the extra when it is missing
- `setup_fastapi_blog(..., admin=False)` adds only the blog (and the REST API) and
  needs no extra. It makes up no default credentials in that mode
- `list_posts` no longer uses `lru_cache`: the cached list is checked against the
  directory signature (`(name, mtime_ns, size)` of the `*.md` files), so edits made
  outside the app are visible without a restart. No TTL, thread-safe, no external
  service. `helpers.clear_posts_cache()` (and `list_posts.cache_clear()`) still work
- The translation helpers moved to `fastapi_blog.i18n` and the translation files to
  `fastapi_blog/translations/` because the public blog uses them.
  `fastapi_blog.admin.i18n` stays as an alias
- Basic auth no longer needs a `SessionMiddleware`: `auth.get_current_user` only
  reads the session when there is one. Credentials are compared with
  `secrets.compare_digest`

#### Added
- `auth_dependency` parameter of `get_api_router()` and `add_editor_to_app()`, and
  `api_auth_dependency` of `add_blog_to_fastapi()`: a custom dependency replaces
  the built-in checks
- `admin_username` and `admin_password` parameters of `add_editor_to_app()`
- `ConfigurationError`: the app fails at startup when the REST API requires
  authentication (`require_auth=True`) and has no credentials, no dependency and
  no `SessionMiddleware`
- CI matrix `core` / `all` extras; tests that need the admin extra are skipped in
  the core run (`tests/conftest.py`)

#### Removed
- Dependencies `redis[hiredis]` and `pyjwt` (they were not used), and all mentions

#### Fixed
- Docstring of `add_blog_to_fastapi` said the admin panel ignores the schema; it
  uses it when given the same schema (done for you by `setup_fastapi_blog`)

#### Deprecated
- Already deprecated and still present: `add_editor_to_app(ui=True)`. Planned for the
  next phases: the `POSTS_DIR` environment variable, the default `admin` /
  `Admin123!` credentials

### Phase B: document storage (in progress)

#### Added
- `fastapi_blog.store`: shared frontmatter parsing (`parse_document`),
  serialization, atomic writes (`atomic_write_text`, temp file + `os.replace`),
  slug/path-escape checks (`safe_document_path`) and an etag primitive
  (`compute_etag`) for later `If-Match` support

#### Fixed
- The blog post page, `helpers.list_posts`, the deprecated editor API and both
  admin post models (`markdown_model.MarkdownPost`, `markdown_crud.MarkdownPost`)
  used to split the file on every `---`, so a Markdown horizontal rule or table
  (`|---|---|`) in the body silently truncated the rendered post. All five now
  parse frontmatter the same way, only at the file's first `---`/`...` boundary
- All file reads/writes across these modules are explicit UTF-8; writes from the
  editor API and the admin post models are atomic (temp file + `os.replace`)
- `admin.markdown_model.MarkdownPost` no longer invents `datetime.now()` for a
  post with no date; a missing date stays `None` (the admin list/sort already
  handled `None` dates for mixed-timezone posts)

#### Still open for this phase
- No `Collection`/`DocumentStore` abstraction yet (4.1, 4.6): the four read/write
  call sites above now share parsing/writing primitives but aren't a single
  service, and `posts`/`pages` aren't yet modeled as two collections
- No `etag`/`If-Match` concurrency on the REST API or the admin save path yet
  (4.7); `store.compute_etag` exists but nothing calls it yet
- `markdown_crud.MarkdownPost` already defaulted an absent date to `''` (not
  `datetime.now()`); only `admin.markdown_model.MarkdownPost` invented a date,
  and that's what this pass fixed

## [Unreleased]

### Added
- **Configurable frontmatter schema** (step 1): `FrontmatterSchema` and `FieldSpec`
  describe frontmatter fields (types, defaults, aliases, semantic roles) in code or
  in a YAML/JSON file and build a Pydantic model on demand
  - `DEFAULT_SCHEMA` and `LOOSE_DEFAULT_SCHEMA` reproduce the old hardcoded behavior
  - `frontmatter_model()` accepts an optional `schema` argument
  - Step 2: the public blog uses the schema roles (`title`, `date`, `published`,
    `tags`, `description`) instead of fixed keys: new `frontmatter_schema`
    parameter of `add_blog_to_fastapi()` and `get_blog_router()`, `schema`
    parameter of `helpers.list_posts()`
  - Post lists hide the date when a post has none; posts without a date go last
  - `slug` and `content` are reserved field names (use an `alias`)
  - Step 3: the REST API validates requests with the schema and writes posts with
    the external keys (aliases): `frontmatter_schema` parameter of
    `get_api_router()` and `add_editor_to_app()` (also passed on by
    `add_blog_to_fastapi(include_api=True)`), `payload_model(strict, schema)`,
    `FrontmatterSchema.payload_model()`
  - `add_editor_to_app(ui=True, frontmatter_schema=...)` warns: the deprecated UI
    keeps the built-in fields
  - Step 4: the admin panel builds the post form, the post list and the dashboard
    from the schema: `frontmatter_schema` parameter of `add_admin_to_app()` and
    `setup_fastapi_blog()` (which passes it to the blog, the REST API and the admin)
  - New `admin/form_fields.py`: input kinds, form values and labels per field type
  - The post list hides the date, status and tags columns when the matching roles
    are not bound; the dashboard shows posts without a date
  - See `docs/FRONTMATTER_SCHEMA.md`
- **i18n for blog routes**: Blog public interface now supports internationalization
  - Added `blog` namespace to translation files (en.yaml, ru.yaml)
  - New parameters: `locales` and `default_locale` in `add_blog_to_fastapi()`
  - Blog responds to `Accept-Language` header for UI localization
  - 10 new i18n tests
- **Unified authentication**: Single auth mechanism for both admin panel and REST API
  - New `auth.py` module with `get_current_user()` and `require_current_user()`
  - Supports both session cookie (admin panel) and HTTP Basic auth (REST API)
  - Same credentials work for both authentication methods
  - 9 new unified auth tests (6 unit + 3 integration)
- Parameters `admin_username` and `admin_password` in `add_blog_to_fastapi()` for API auth

### Fixed
- `require_authentication()` now handles missing SessionMiddleware gracefully
- `.git.bak` directory removed from repository (technical debt cleanup)

### Changed
- REST API can now use unified auth when credentials are provided
- Blog templates updated to use translation keys via `{{ t.blog.* }}`

---

## [0.8.1] - 2026-05-15

### Added
- `setup_fastapi_blog()` unified facade for one-step blog and admin initialization
- Validation for weak `secret_key` with `UserWarning` and generation examples
- `.env.example` with documentation for all environment variables
- Comprehensive test coverage:
  - Password logging protection (3 tests)
  - Weak secret validation (6 tests)
  - Unified facade setup (5 tests)
  - Theme switcher template inheritance (7 tests)
  - Total: 88 tests (+21 new)
- `CONTRIBUTING.md` with guidelines for contributors

### Fixed
- **CRITICAL**: Admin password no longer logged to stdout at application startup
- Lifespan composition: user's `lifespan` correctly wrapped instead of replaced
- Parameter name: `posts_dir` → `posts_dirname` in `setup_fastapi_blog()` for consistency
- `test_lifespan.py`: use in-memory SQLite and async inspector for reliability
- Theme switcher tests: exact assertions instead of `or`-checks, full inheritance chain verified

### Security
- **CRITICAL**: Passwords never logged, not even at DEBUG level
- Weak `secret_key` detection (< 32 chars or known weak values) with user-friendly warnings
- Environment variable best practices documented in `.env.example`

### Changed
- All `print()` statements in `admin/__init__.py` replaced with proper logging
- Repository URLs updated from `awestley/fastapi-blog` to `pydanny/fastapi-blog`
- README: added development fork notice
- QUICKSTART: added prerequisites, environment variables, role management sections

### Removed
- Deprecated parameters from `add_admin_to_app()`:
  - `base_url` (replaced by automatic locale-based URLs)
  - `i18n_enabled` (use `locales` parameter)
  - `i18n_default_locale` (use `default_locale` parameter)
  - `i18n_locales` (use `locales` parameter)

---

## [0.8.0] - 2026-05-12

### Added
- Admin panel powered by starlette-admin
- Role-based access control (RBAC) with `enable_role_management` flag
- Internationalization (i18n) for English and Russian locales
- Separate admin instances per locale (`/admin/en`, `/admin/ru`)
- Markdown CRUD for managing blog posts from admin panel
- Custom fields: `MarkdownField`, `TagsField`, `SlugField`
- Theme switcher (light/dark/auto) on all admin ModelView pages
- RBAC: role management accessible only to root admin user
- Dropdown menu for access control section
- Template isolation: admin templates separate from public blog templates
- Password hashing with bcrypt for secure credential storage
- Session-based authentication for admin panel

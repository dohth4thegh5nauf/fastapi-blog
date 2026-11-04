# The project file: `fastapi_blog.yaml`

The command line (`python -m fastapi_blog check|export`) needs to know
where the collections live. A small YAML file in the project root names
them:

```yaml
collections:
  notes:
    dir: content/notes            # relative to the project root (required)
    schema: content/notes.schema.yaml   # optional
    slug_pattern: '[0-9]{4}-[a-z0-9-]+'  # optional
    extension: [md, markdown]     # optional, one extension or several
    create: false                 # optional, refuse new documents (default true)
    delete: false                 # optional, refuse deletions (default true)
    slug:                         # optional, how {title_slug} is made
      encoding: unicode           # unicode (default) or ascii
      clean_accents: false        # é -> e before sanitizing
      sanitize_replacement: '-'   # replaces every run of other characters
    slug_template: '{seq|pad(4)}-{title_slug}'  # optional, generates slugs
    unique: [seq]                 # optional, values that must not repeat
    summary: '{status} · {title}' # optional, caption in lists and `check`
    check:                        # optional, integrity checks (see below)
      links: off                  # off (default), warn or error
      files: off                  # off (default), warn or error
    validators:                   # optional, see below
      - name: lint
        argv: [markdownlint, '{path}']
        exit_map: {0: ok, 1: error, 2: undefined}
        unavailable: undefined
        timeout: 20
        blocking: [error, undefined]
```

The YAML `dir` setting is a static path relative to the project file. Python
applications that need tenant- or request-specific storage can instead pass a
`CollectionSpec` whose `dir` is a callable accepting the current Starlette
request and returning an absolute path. The resolved path is cached on that
request and shared by the public blog, REST API, admin Markdown views,
health-checks, and SEO routes. This is a runtime application API; project-file
commands such as `check` and `export` require a static directory.

## Multi-locale collections

A project-level `i18n` block supplies defaults to every collection. A
collection may inherit those defaults, disable i18n with `i18n: false`, or
override selected options with its own mapping. The optional
`translations_dir` points to project-owned YAML files that extend the bundled
admin/public UI translations:

```yaml
translations_dir: translations

i18n:
  structure: multiple_files
  locales: [en, ru, de]
  default_locale: en
  omit_default_locale_suffix: true
  fallback: default
  translate_body: true
  required_in_translations: false
  write_duplicates: false

collections:
  notes:
    dir: content/notes
    label: {en: Notes, ru: Заметки, de: Notizen}
    i18n: true
    check:
      translations: warn
```

The supported layouts are `multiple_files`
(`<slug>.<locale>.md`, with the default suffix optionally omitted) and
`multiple_folders` (`<locale>/<slug>.md`). `single_file` is rejected. For a
collection that keeps its canonical documents directly in the collection
directory and stores translations below locale directories, set
`default_locale_in_root: true` with `multiple_folders`. Default-locale files
left under the default locale directory are rejected with a configuration
error so they cannot disappear silently; move them to the collection root.
Locale
suffixes and directories are recognized only when the locale is listed in
`locales`. i18n is rejected for collections with `depth` greater than zero.
The slug is canonical across locales and is derived from the default-locale
document. A translation cannot create or rename a slug.

`DocumentService` validates and writes localized documents, checks per-locale
and entry ETags, and coordinates multi-locale writes and change notifications.
The service stages files and rolls back a failed replacement, but a write to
several files is not atomic to readers: they may observe intermediate states.
Locks coordinate writers in the same process only; separate processes need
external coordination. A crash during a multi-file operation can also leave
an incomplete update or staged files requiring recovery.
The REST API exposes localized reads and writes at the collection document
route. The admin provides locale tabs, fallback indication, locale chips and
a side-by-side canonical preview with a link to edit the source. The editor
keeps changed locale drafts in the current browser tab and submits them in one
batch with rollback on write failure. Concurrent readers can still observe
intermediate file states. The save endpoint also accepts explicit per-locale
ETags for batch callers.
Deleting an entry with translations requires an explicit cascade request.
The optional document policy and field transitions are experimental; the
existing collection-level permissions still apply. The document policy
applies to REST and admin document operations. The public blog frontend is
outside the scope of multilingual collections and is not filtered by this
hook. Do not rely on the hook as a complete access-control boundary.

The current experimental Python hook is configured with
`CollectionSpec(document_authorize=callback)`. It is called synchronously
with `(user, action, collection, slug, locale, before, after)`, where
`before` and `after` are frontmatter mappings. Return `True` to allow an
operation; `False` or a reason string denies it. It supplements the existing
collection-level authorization. For generated-slug creates, the service
computes the slug under the collection lock and calls the hook with it before
writing the file.
Autocomplete and collection-wide diagnostics are suppressed for protected
collections.

An experimental schema field may specify `transitions` with `initial` and
`allowed` lists. Each allowed rule has `from`, `to`, and an optional
`permission`. Permission-bearing transitions require a document policy and
ask it to allow both the named permission and the `transition` action.
These checks cover scalar fields and nested objects. Transitions inside
`list[object]` are rejected at schema load because rows have no stable identity
for safe matching after reordering. The admin disables choices that violate
the transition rules or their document policy. The service still rejects
invalid transitions when a save is submitted.
`check` reports missing, orphaned, unknown-locale and mismatched duplicate
translations according to `check.translations`.

`FieldSpec.i18n` controls content storage: `translate` (also `true`) stores
locale-specific values, `duplicate` compares a value with the canonical
locale, and `none` is not localized. `required_in_translations` controls
whether required fields may be omitted in translations; `write_duplicates`
controls whether duplicate values are mirrored to translation files.
If an existing translation contains a shared field that differs from its
canonical value, saving that translation is rejected with a conflict. Resolve
the existing value first so a save cannot silently discard it.

`label`, `hint`, `choices[].label` and collection `label` can be strings or
locale maps. Resolution order is interface locale, collection default locale,
then the first mapping entry. Unknown locale keys produce a configuration
warning.

The optional `translations_dir` must be a relative directory inside the
project. A file named `<locale>.yaml` is deep-merged over the bundled file for
that locale; missing entries fall back to English and are logged. Locale
names come from the `locale.name` value in those YAML files; for a configured
locale without a translation file, the code is used as its display name.

## External validators (TODO 6.2)

A validator runs a command **without a shell** (an argument list) on every
document, with a timeout, a small environment and capped output. Its exit
code maps to an outcome via `exit_map` (unlisted codes are `undefined`):
`ok`, `warning`, `error` or `undefined` — the last one means "couldn't be
checked" and is never treated as fine.

Placeholders in `argv`: `{path}` (the document's path relative to the
project root), `{slug}`, `{collection}`, `{locale}` and `{fields.NAME}` (a
scalar frontmatter field). Values other than `{path}` must match
`[A-Za-z0-9._:-]+`; all values must be nonempty and must not start with `-`,
otherwise the check fails with `validator.NAME.unsafe_value` and
the command is **not** started. A missing command or a timeout gives the
`unavailable` outcome.

`run` may be `write`, `check` or `both` (the default). `write` validators run only on writes; `check` validators run only during project checks. For localized writes, the validator runs once for each changed locale file.
During localized writes, `{path}` names the staged file containing the
proposed document, rather than the final file name.

`blocking` lists the outcomes that refuse a write through the REST API
(TODO 6.3): the file is rolled back to its previous bytes (a just-created
file is removed) and the request gets HTTP 422 with the findings in the
body. Note the documented limitation: between the write and a rollback the
new content is visible to concurrent readers.

## Slug templates, uniqueness and summaries (TODO 6.4)

With `slug_template` set, `POST /api/posts/create` and the admin form (an
empty slug field) generate the file name once, at the first save; later
edits don't rename the file. The template language is shared with
`jsonld.id_template`, `summary` and validator arguments: `{name}` is a
service tag or a frontmatter field, `{fields.NAME}` addresses a field whose
name collides with a tag, and filters chain as `{name|filter(arg)}`
(`lower`, `upper`, `truncate(n)`, `default(x)`, `pad(n)`, `date(fmt)`).
Unknown tags or filters fail when the project file loads.

Service tags for slugs: `seq` (the next free sequence number, allocated
under the store lock), `title_slug` (the title-role field, sanitized per the
`slug` options and capped at 200 bytes), `year`/`month`/`day` (the
date-role field, or the first-save UTC time when it is absent), `collection`
and, for nested collections, `dirname`.

`unique` lists field names (or `seq`) whose values must not repeat; `check`
reports duplicates, and creating a document with a duplicate value fails
with HTTP 409.

`summary` renders the caption shown under the title in the admin list and
next to findings in the human-readable `check` output; without it the
title-role field is used. Allowed tags: `slug`, `collection`, `dirname`,
`filename` and any field.

`create: false` refuses to create new documents, `delete: false` refuses
deletions; both apply in the storage layer, the REST API (HTTP 403) and the
admin panel.

## Precedence

**An explicit CLI flag beats the project file, the project file beats the
built-in defaults** (`posts/` with the built-in frontmatter schema):

```bash
# Uses fastapi_blog.yaml (its `notes` collection, or `posts` if present,
# or the only collection there is):
python -m fastapi_blog check

# Explicit name, explicit overrides:
python -m fastapi_blog export --collection notes --posts-dir elsewhere
```

- `--posts-dir` overrides the `dir` of the selected collection.
- `--schema` overrides its `schema`.
- `--collection NAME` selects a collection by name (without a project
  file it is just the collection's name, as before).

The file is only read where the command runs — there is no search up the
directory tree. Applications that use the library in code don't need the
file: they keep passing `posts_dirname`/`frontmatter_schema` to
`add_blog_to_fastapi()`.

## The `check` command

```bash
python -m fastapi_blog check [--collection NAME] [--json] [--fail-on error|warning]
```

Checks every document of the selected collections: the file parses, the
frontmatter matches the schema, unique values don't repeat, `link` fields
resolve to an existing document that passes the field's `filters`, `file`/
`image` fields point at an existing file inside `media_dir`, and (with a
`jsonld` section) the context covers every schema key. `check.links` and
`check.files` select the level (`off` by default) of the last two checks.
Exit codes: `0` clean, `1` findings at or above `--fail-on`, `2` no findings
but something could not be checked (`undefined` — never reported as clean),
`64` usage/configuration error.

---

**Last Updated:** 2026-10-31
**Version:** 0.9.0 (in development)

## Change notifications (TODO 6.5)

A collection may receive a Python callback after a successful create, update
or delete. The callback is not configured in YAML; attach it to the
`CollectionSpec` loaded from the project file:

```python
from dataclasses import replace
from fastapi import FastAPI
from fastapi_blog import add_editor_to_app, load_project


def publish_change(event):
  # Send a message to a queue, trigger a rebuild, or create a Git commit.
  print(event.kind, event.collection, event.slug, event.etag, event.user)


project = load_project('fastapi_blog.yaml')
posts = replace(project.collections['posts'], on_change=publish_change)
app = FastAPI()


async def authenticate():
  return {'username': 'content-editor'}


add_editor_to_app(
  app,
  ui=False,
  collection_spec=posts,
  auth_dependency=authenticate,
)
```

The immutable event has `kind` (`created`, `updated` or `deleted`),
`collection`, `slug`, `etag` and `user`. The etag is the new content hash for
create/update and `None` for delete. REST requests pass the authenticated
username (or user id) when available; direct storage calls may pass `user=`
to `DocumentStore.write()`/`delete()`. The hook runs after the mutation and
outside the store lock. Exceptions are logged and swallowed: a notification
failure does not undo a successful file operation. No event journal or retry
queue is maintained; the application owns delivery and durability.

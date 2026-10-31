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

## External validators (TODO 6.2)

A validator runs a command **without a shell** (an argument list) on every
document, with a timeout, a small environment and capped output. Its exit
code maps to an outcome via `exit_map` (unlisted codes are `undefined`):
`ok`, `warning`, `error` or `undefined` — the last one means "couldn't be
checked" and is never treated as fine.

Placeholders in `argv`: `{path}` (the document's path relative to the
project root), `{slug}`, `{collection}` and `{fields.NAME}` (a scalar
frontmatter field). Values must match `[A-Za-z0-9._:-]+` and must not start
with `-`, otherwise the check fails with `validator.NAME.unsafe_value` and
the command is **not** started. A missing command or a timeout gives the
`unavailable` outcome.

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

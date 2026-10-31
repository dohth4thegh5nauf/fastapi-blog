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

The format covers only what is implemented; `slug_template`, `unique` and
the `check` options (TODO 6.4) will extend it when they land.

## The `check` command

```bash
python -m fastapi_blog check [--collection NAME] [--json] [--fail-on error|warning]
```

Checks every document of the selected collections: the file parses, the
frontmatter matches the schema, and (with a `jsonld` section) the context
covers every schema key. Exit codes: `0` clean, `1` findings at or above
`--fail-on`, `2` no findings but something could not be checked
(`undefined` — never reported as clean), `64` usage/configuration error.

---

**Last Updated:** 2026-10-31
**Version:** 0.9.0 (in development)

# Release checklist: 0.9.0

This checklist is the release gate for the 0.9.0 package. The project version
is already `0.9.0`; the changelog remains `Unreleased` until every required
verification below has passed on the release candidate.

## Phase E acceptance

| Criterion | Implementation | Regression coverage / verification |
| --- | --- | --- |
| One authorization policy for API, Markdown CustomViews and SQLAlchemy ModelViews | `permissions.py`, `editor.py`, `admin/markdown_crud.py`, `admin/views.py`, `admin/views_role.py` | `tests/test_permissions_security.py`, `tests/test_role_management_access.py`, `tests/test_schema_admin.py` |
| `admin`, `editor`, `viewer` action matrix; unknown roles/resources/actions denied | `permissions.py` and admin view hooks | Permission and role-management tests; `is_action_allowed` is async for starlette-admin 1.0.3 |
| Legacy authenticated principals without a role remain compatible under the default policy; custom `authorize=` replaces the default policy | `permissions.py`, `docs/ROLE_MANAGEMENT.md` | Role-management and permission regression tests |
| No production default password or weak session secret; legacy development credentials require explicit `insecure_dev=True` | `security.py`, `admin/__init__.py`, `main.py` | Configuration/security tests for missing, weak and explicit development settings |
| Cookie settings and CSRF boundary | `security.py`; Starlette Admin CSRF remains active; Origin guard is REST API-only | Security tests for `SameSite`, `Secure`, Origin/Host and no duplicated admin Origin guard |
| Direct bcrypt support | `admin/passwords.py` | Password hashing and legacy hash verification tests |
| Admin writes through `DocumentService`, not its own REST endpoint | `service.py`, `admin/markdown_crud.py` | `tests/test_document_service.py`, `tests/test_markdown_crud.py` |
| Schema-driven controls: select, pattern/message, filtered link autocomplete, object/list groups, hidden/read-only | `admin/form_fields.py`, `admin/templates/markdown_edit.html` | `tests/test_schema_admin.py`; list-valued link filters are covered |
| Diagnostics, ETag conflicts, write-time schema rules, uniqueness and blocking validators | `service.py`, `admin/markdown_crud.py` | `tests/test_document_service.py`, schema/admin integration tests |
| Sanitized live preview by default | `MarkdownSaveView.preview`, `helpers.markdown`, `sanitize_html` setting | `tests/test_markdown_crud.py`; explicit `sanitize_html=False` is the documented trusted-content opt-out |
| Shared admin theme/language switcher | `admin/templates/layout.html` | Existing role/user/admin template tests |
| Diff/history | Not included: TODO 7.9 is MAY and out of scope | No release blocker |

## Required release verification

Run from the repository root using the locked dependency set and supported
Python versions (3.12 through 3.15):

```bash
uv sync --locked --extra dev --extra admin --extra jsonld
make all
```

Run the GitHub workflows on the current release candidate before marking this
checklist complete. A push starts the Tier 1 validation workflow; a pull request
targeting `main` starts the Tier 2 test, API/Compose and security workflows. The
CI matrix (see `.github/workflows/`) must pass before release:

- Tier 1 `push-validate` — ruff, format, mypy, gitleaks on every push;
- Tier 2 `pr-test-fastapi-blog` — Python 3.12–3.15, `core` and `all` extras;
- Tier 2 `pr-scan-security` — bandit (SAST), pip-audit (SCA) on the locked
  runtime set, conditional CodeQL, and the package build;
- Tier 2 `pr-test-api` — Compose model validation, Trivy OS scan and an
  API/contract smoke against the running container and its health probes.

Trivy is configured with `severity: CRITICAL,HIGH`, `ignore-unfixed: true`
and `exit-code: 1`. The first run may therefore fail deliberately when the
base image contains a HIGH/CRITICAL OS vulnerability with an available fix.
Treat that as a security finding to investigate and resolve or document; do
not change the exit code or severity threshold merely to make CI green. The
last reported API Contract run failed during Trivy installation, before the
scan started. Commit `dea11a0` downloads the pinned release archive and
verifies its checksum. The pull request CI passed after this change, including
the Trivy scan.

This repository is a private development source. Branch protection here is
not a release gate; release preparation and publication happen in the
destination repository. Decide its access and protection policy there.

Before publishing the final candidate, verify the source distribution and
wheel contain the expected package templates and translations, install the
wheel in a clean environment, and run smoke tests for
`setup_fastapi_blog(admin=False)` and the admin extra. Confirm that missing
credentials fail at startup and that no development credentials are enabled
implicitly. Repeat this manual gate against the final release commit in the destination
repository, since any migration or release metadata changes alter the candidate. On the tagged release, also update
`compose.yaml`'s `image: fastapi-blog:<version>` to match the published image
tag (currently the file says `fastapi-blog:0.9.0`) and validate with
`docker compose config --quiet`.

## Evidence and current state

After commit `58d1f23`, the local Python 3.12 gate passed with **893 passed,
2 skipped**. Pytest treated unhandled thread exceptions as errors; Ruff,
formatting and mypy also passed. The latest pull request CI passed on the
current candidate, including the Python 3.12–3.15 matrix and the API/Trivy
workflow. Repeat the gate if source changes after that PR run.
Note for maintainers: `make all` relies on `uv run`, which requires the exact
interpreter pinned in `.python-version` (3.12.16); where that patch version is
unavailable, run the same commands from the project's `.venv` directly.

Release verification performed locally on top of the test gate:

- `bandit -r src/` — clean, exit 0 (ten intentional low-severity findings
  annotated with `nosec`: guarded asserts, the validator subprocess with a
  configuration-fixed argument list and no shell, ElementTree generating
  the sitemap). Without the annotations the CI security step could never
  pass, since `bandit` exits non-zero on any finding.
- `safety check --ignore 70612` on the locked dependency set — no
  vulnerabilities in project dependencies (only the venv's own `pip`
  reported CVEs, which the CI image does not install from this lock). The
  CI gate uses `pip-audit` over the exported lock instead (same class of
  check, no API key needed).
- Health probes: eight tests cover the draft-06 format, the HTTP status
  semantics (`pass` → 2xx, `fail` → 503) and the default-on behavior plus explicit opt-out. The Compose
  stack was also smoke-tested locally against a Docker daemon:
  `docker compose up --build --wait` reaches `healthy`, all three probes
  answer `pass` as `application/health+json` with the specified
  `Cache-Control` lifetimes, and `/blog/`, a published post, the root
  redirect and `/ru/blog/` all respond; CI repeats this in `pr-test-api`.
- `python -m build` — `fastapi_blog-0.9.0` sdist and wheel build cleanly;
  both contain the admin/public templates.
- Clean-environment smoke (wheel installed into a fresh venv with the locked
  runtime set): core import keeps extras lazy (`starlette_admin`,
  `sqlalchemy` absent from `sys.modules`), `setup_fastapi_blog(admin=False,
  include_api=True)` serves the blog and rejects unauthenticated API reads
  with 401, and an API without any authentication mechanism fails at
  startup with `ConfigurationError` (TODO 3.3). With the `admin` extra,
  `add_admin_to_app` without credentials raises `ConfigurationError`, and
  with an explicit password and strong secret it mounts the `en`/`ru`
  panels.

## Handoff to the release repository

- Transfer the intended commit and history to the destination chosen by the
  maintainer. Preserve the upstream attribution and license.
- Replace the upstream project URLs in `pyproject.toml` and clone instructions
  in `README.md`, `CONTRIBUTING.md` and `QUICKSTART.md` with the confirmed
  destination URLs. Keep references that intentionally identify the upstream
  fork. Verify ownership and availability of the package name before publishing.
- Review the destination's GitHub Actions settings, credentials and publishing
  permissions. `push-publish-docker.yaml` uses `github.repository` for GHCR;
  pushes to `main` and version tags publish images under the destination owner.
  Check registry visibility, retention of candidate tags, optional CodeQL and
  Codecov configuration before enabling the workflows.
- Update the changelog date and confirm the Compose image tag. Run CI and the
  clean wheel smoke tests on the final release commit, then tag and publish
  through the release repository's approved channels.

The candidate commit `6bc4dd0` passed the pull request workflows: Test
fastapi-blog, Validate PR, Security and API Contract (run IDs
`41859106470`, `41859106420`, `41859106442` and `41859106643`). Its push
validation also passed (`41859093360`). The full local `make all` gate passed
on Python 3.12: Ruff, formatting and mypy were clean; pytest collected
**932 tests** and completed with **930 passed, 2 skipped**; total coverage was
**87%**. The full test run needs access to local async SQLite and was run
outside the restricted sandbox. This checklist update does not change package
source; keep the 0.9.0 changes under `[Unreleased]` until the final release
commit passes CI and the release-repository checks in the handoff section are
complete.

On 2026-11-04, `uv build` produced the 0.9.0 sdist and wheel from the same
package source as candidate `6bc4dd0`. Both artifacts contained the public and
admin templates and English/Russian translation files. Fresh environments
installed from the wheel using the locked core and admin runtime sets. Core
smoke confirmed lazy admin/SQLAlchemy imports, a rendered blog post, a 401 for
an unauthenticated API request, and startup rejection without API credentials.
Admin smoke confirmed configuration rejects missing credentials and mounts
the `en` and `ru` admin panels with valid credentials.

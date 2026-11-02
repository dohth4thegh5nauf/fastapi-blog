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
Python versions (3.12 and 3.13):

```bash
uv sync --extra dev --extra admin --extra jsonld
make all
```

The CI matrix (see `.github/workflows/`) must also pass:

- Tier 1 `push-validate` — ruff, format, mypy, gitleaks on every push;
- Tier 2 `pr-test` — Python 3.12 and 3.13, `core` and `all` extras;
- Tier 2 `pr-scan-security` — bandit (SAST), pip-audit (SCA) on the locked
  runtime set, CodeQL, and the package build;
- Tier 2 `pr-test-integration` — Compose smoke against the running
  container and its health probes.

Before publishing, verify the source distribution and wheel contain the
expected package templates and translations, install the wheel in a clean
environment, and run the smoke tests for `setup_fastapi_blog(admin=False)` and
for the admin extra. Confirm that missing credentials fail at startup and that
no development credentials are enabled implicitly.

## Evidence and current state

The final release-candidate review re-ran the full gate in the locked
environment (Python 3.12): `make all` is green — Ruff checks, format
verification, mypy and the complete pytest suite report **759 passed,
2 skipped**. The same suite was also run against the locked dependency set
from a clean environment (`uv pip install -e '.[dev,admin,jsonld]'`,
fastapi 0.162 / starlette 1.10 / starlette-admin 1.0.3): **759 passed,
2 skipped** there as well. The review also fixed the `f.items` template
lookup (Jinja resolved it to the dict method, breaking `list[object]`
rendering), aligned four newly added tests with the strict schema and the
service contract, and landed the single write-transaction refactor.

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
- Health probes: six new tests cover the draft-06 format, the HTTP status
  semantics (`pass` → 2xx, `fail` → 503) and the opt-in flag; the Compose
  stack validates end to end in CI (`pr-test-integration`).
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

What remains before publishing: push the branch and let the CI matrix run
(Python 3.13 in particular was not exercised locally), set the changelog
release date, build the final artifacts from the tagged commit, and publish.

**Release status: locally verified; CI acceptance and tagging pending.**
Keep `CHANGELOG.md` at `[0.9.0] - Unreleased` until the CI matrix above is
green.

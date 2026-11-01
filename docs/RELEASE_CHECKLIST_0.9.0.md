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

The CI matrix must also pass:

- Python 3.12 and 3.13, `core` installation/test job;
- Python 3.12 and 3.13, `all` extras/test job;
- security checks (`safety` and `bandit`) as configured by the workflow.

Before publishing, verify the source distribution and wheel contain the
expected package templates and translations, install the wheel in a clean
environment, and run the smoke tests for `setup_fastapi_blog(admin=False)` and
for the admin extra. Confirm that missing credentials fail at startup and that
no development credentials are enabled implicitly.

## Evidence and current state

The final release-candidate review re-ran the full gate in the locked
environment (Python 3.12): `make all` is green — Ruff checks, format
verification, mypy and the complete pytest suite report **759 passed,
2 skipped**. This run covers the service-backed form and preview changes; it
supersedes the earlier 750-test report. The review also fixed the
`f.items` template lookup (Jinja resolved it to the dict method, breaking
`list[object]` rendering) and aligned four newly added tests with the strict
schema and the service contract.

The CI matrix (Python 3.12 and 3.13, `core` and `all` jobs, security checks)
still has to pass on the release candidate; the local run does not replace it.

**Release status: implementation complete; final CI acceptance pending.**
Keep `CHANGELOG.md` at `[0.9.0] - Unreleased` until the release verification
above is green. Do not create a git tag or commit as part of this preparation.

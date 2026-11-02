# GitHub Actions

This repository contains one deployable Python package (`fastapi-blog`), so
there is one Python validation/test scope rather than a service matrix.

## Tiers

| Tier | Workflow | Trigger | Responsibility |
|---|---|---|---|
| 1 | `push-validate.yaml` | Every push | Lock consistency, Ruff format/lint, mypy and Gitleaks |
| 1 | `pr-validate.yaml` | PR to `main` | Same fast validation on the PR merge ref |
| 2 | `pr-test-fastapi-blog.yaml` | PR to `main` | Full package pytest suite, coverage, Python 3.12/3.13 × core/all extras |
| 2 | `pr-test-api.yaml` | PR to `main` | Compose model validation, container build, Trivy OS scan, API/Contract smoke |
| 2 | `pr-scan-security.yaml` | PR to `main` | Bandit SAST, pip-audit SCA, CodeQL and package build |
| Publish | `push-publish-docker.yaml` | Push to `main` or `v*.*.*` tag | Build, attest and publish the image to GHCR |

The Compose workflow owns pull-request container builds. The publish workflow
therefore does not build a second copy of the same image on PRs.

## Reuse and security

- `.github/actions/setup-python-env/action.yaml` is the shared composite action
  for the pinned Python/uv setup used by Python jobs.
- `reusable-validate-python.yaml` factors the full Tier 1 job because both
  push and PR trigger wrappers call it. Other jobs remain inline because they
  are not reused as complete jobs.
- All workflows start with `permissions: {}`. Permissions are granted per job.
- Third-party actions are pinned to full commit SHAs with release comments.
- The Python project is installed from `uv.lock` using `uv sync --locked`.
  Tier 1 syncs the dev, admin and JSON-LD extras because mypy needs the
  optional imports resolvable; the test matrix keeps a core leg (dev only)
  to prove the package works without its optional extras. Every `uv run`
  restates its extras explicitly (`$UV_EXTRAS`), matching the Makefile.
  Security scanner tools are invoked with exact direct versions.
- Contributor-list regeneration is intentionally outside CI: the existing
  third-party action still declares the retired Node 20 runtime, and creating
  PRs with `GITHUB_TOKEN` would not trigger the required PR workflows. A PAT
  workaround would violate the least-privilege direction of this design.
- Docker publishing alone receives `packages: write`; pull-request workflows
  do not receive registry write permissions. Multi-architecture builds use
  QEMU and pinned `binfmt`/BuildKit images.
- Concurrency cancels obsolete Tier 1/2 runs. Publishing is not cancelled
  mid-flight.

## Required status checks

Configure branch protection for `main` in GitHub Settings. Require these
stable job checks:

- `Validate PR / validate-required`
- `Test fastapi-blog / tests-passed`
- `API Contract / api-smoke`
- `Security / security-passed`

The aggregate jobs fail if any reusable-workflow, matrix or security leg
fails, while avoiding nested/matrix-generated required-check names that change
when implementation details change.
`Validate / validate` is the Tier 1 push signal; `Validate PR / validate-required`
is the fast required PR check and complements the full Tier 2 checks.

## Tier 3 scope

No scheduled E2E, performance or DAST workflow is configured. This repository
does not define a staging endpoint, browser test suite or performance
baseline, so adding those jobs now would either be non-functional or test an
invented environment. Add Tier 3 when a real target and acceptance threshold
are defined.

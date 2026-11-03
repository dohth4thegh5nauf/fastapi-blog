"""Health-check endpoints in the draft-inadarei-api-health-check-06 format.

Three probes, as fixed in the project health-check specification:

- ``/api/v1/health`` — base probe: the full report with per-component checks;
- ``/api/v1/health/live`` — liveness: touches no dependency, answers ``pass``
  whenever the process responds at all;
- ``/api/v1/health/ready`` — readiness: the same critical check as the base
  probe, but without the detailed topology.

HTTP semantics: ``pass``/``warn`` answer 2xx-3xx, ``fail`` answers 4xx-5xx
(503). All responses carry ``Content-Type: application/health+json`` and a
``Cache-Control`` lifetime.

The package has no hard external dependencies (the file system is the only
mandatory backend, TODO П1), so the only critical readiness check is that
the content directories of the mounted collections are readable. The admin
panel's optional SQL database is intentionally not probed here: it is not a
critical dependency for serving content.
"""

import datetime
import os
import time
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as package_version
from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse, Response


_PROCESS_START = time.monotonic()

# Probe lifetimes in seconds: short for the probes orchestrators poll,
# longer for the detailed base report used by monitoring.
_LIVE_READY_MAX_AGE = 5
_BASE_MAX_AGE = 60

_MINIMAL_HEALTH_SCHEMA: dict[str, Any] = {
  'type': 'object',
  'required': ['status'],
  'properties': {
    'status': {'type': 'string', 'enum': ['pass', 'fail', 'warn']},
  },
  'additionalProperties': True,
}
_BASE_HEALTH_SCHEMA: dict[str, Any] = {
  **_MINIMAL_HEALTH_SCHEMA,
  'properties': {
    **_MINIMAL_HEALTH_SCHEMA['properties'],
    'version': {'type': 'string'},
    'releaseId': {'type': 'string'},
    'notes': {'type': 'array', 'items': {'type': 'string'}},
    'output': {'type': 'string'},
    'serviceId': {'type': 'string'},
    'description': {'type': 'string'},
    'checks': {
      'type': 'object',
      'additionalProperties': {
        'type': 'array',
        'items': {'type': 'object', 'additionalProperties': True},
      },
    },
    'links': {
      'type': 'object',
      'additionalProperties': {'type': 'string', 'format': 'uri'},
    },
  },
}


def _documented_responses(
  schema: dict[str, Any], *, include_failure: bool
) -> dict[int | str, dict[str, Any]]:
  """Describe the custom health media type without advertising JSON instead."""
  success = {
    'description': 'Health report',
    'content': {'application/health+json': {'schema': schema}},
  }
  responses: dict[int | str, dict[str, Any]] = {200: success}
  if include_failure:
    responses[503] = {
      'description': 'A critical health check failed',
      'content': {'application/health+json': {'schema': schema}},
    }
  return responses


def _service_version() -> str:
  """Return the installed distribution version, or a neutral fallback."""
  try:
    return package_version('fastapi-blog')
  except PackageNotFoundError:
    return '0+unknown'


def _now() -> str:
  """Return the current UTC time in ISO 8601."""
  return datetime.datetime.now(datetime.UTC).isoformat()


def _uptime_check() -> dict[str, Any]:
  """Build the ``uptime`` observation (monotonic, never leaves the process)."""
  return {
    'componentType': 'system',
    'observedValue': round(time.monotonic() - _PROCESS_START, 3),
    'observedUnit': 's',
    'status': 'pass',
    'time': _now(),
  }


def _readability_problem(directories: list[str]) -> str | None:
  """Return a short description of the first unreadable directory, if any."""
  for directory in directories:
    if os.path.isdir(directory) and not os.access(directory, os.R_OK):
      return f'Content directory {directory!r} is not readable'
  return None


def _response(
  report: dict[str, Any], *, max_age: int, status_code: int = 200
) -> JSONResponse:
  """Serialize a health report with the registered media type and lifetime."""
  return JSONResponse(
    report,
    status_code=status_code,
    media_type='application/health+json',
    headers={'Cache-Control': f'max-age={max_age}'},
  )


def get_health_router(content_directories: list[str]) -> APIRouter:
  """Build the health router probing the given content directories.

  Args:
      content_directories: Directories whose readability is critical for
          serving content (typically the collection directories). Missing
          directories are not a failure: a collection may be empty until
          the first document is written.

  Returns:
      An ``APIRouter`` with the three ``/health`` probes; mount it where
      the project specification fixes the paths.

  """
  router = APIRouter(tags=['health'])

  @router.get(
    '/health',
    response_class=Response,
    responses=_documented_responses(_BASE_HEALTH_SCHEMA, include_failure=True),
    summary='Service health report',
    description=(
      'Detailed health report, including version and per-component checks. '
      'A failed critical check returns HTTP 503.'
    ),
  )
  async def base_probe() -> Response:
    """Full report with per-component checks for monitoring."""
    report: dict[str, Any] = {
      'status': 'pass',
      'version': _service_version(),
      'checks': {'uptime': [_uptime_check()]},
    }
    problem = _readability_problem(content_directories)
    if problem is not None:
      report['status'] = 'fail'
      report['output'] = problem
      report['checks']['content:readability'] = [
        {
          'componentType': 'datastore',
          'status': 'fail',
          'time': _now(),
          'output': problem,
        }
      ]
      return _response(report, max_age=_BASE_MAX_AGE, status_code=503)
    return _response(report, max_age=_BASE_MAX_AGE)

  @router.get(
    '/health/live',
    response_class=Response,
    responses=_documented_responses(
      _MINIMAL_HEALTH_SCHEMA, include_failure=False
    ),
    summary='Liveness probe',
    description=(
      'Checks that the process responds. Does not access external '
      'dependencies and returns HTTP 200 when the process is alive.'
    ),
  )
  async def live_probe() -> Response:
    """Liveness: the process answers; no dependency is touched."""
    return _response({'status': 'pass'}, max_age=_LIVE_READY_MAX_AGE)

  @router.get(
    '/health/ready',
    response_class=Response,
    responses=_documented_responses(
      _MINIMAL_HEALTH_SCHEMA, include_failure=True
    ),
    summary='Readiness probe',
    description=(
      'Checks whether the service can accept traffic. Returns HTTP 503 '
      'when a critical dependency is unavailable.'
    ),
  )
  async def ready_probe() -> Response:
    """Readiness: critical dependencies only, without the details."""
    problem = _readability_problem(content_directories)
    if problem is not None:
      return _response(
        {'status': 'fail', 'output': problem},
        max_age=_LIVE_READY_MAX_AGE,
        status_code=503,
      )
    return _response({'status': 'pass'}, max_age=_LIVE_READY_MAX_AGE)

  return router

"""External validators of documents (TODO 6.2).

A validator is a command listed in the configuration of a collection (the
`validators:` key of a project file, TODO 6.1). It is run without a shell
(an argument list), with a short timeout, a small environment and a capped
output. Its exit code is mapped to an outcome:

- `ok`: the document is fine;
- `error` or `warning`: a finding;
- `undefined`: the check could not be done (the tool is missing, it timed
  out, or its exit code says so). It is never treated as `ok` (П4).

The command comes only from the configuration, never from a document or a
request. Placeholders in the arguments — `{path}`, `{slug}`, `{collection}`
and `{fields.NAME}` — are replaced with values checked against a strict
character set, so a field value can't add arguments or shell syntax. `cwd`
of the command is the project root.
"""

import dataclasses
import os
import pathlib
import re
import subprocess
from collections.abc import Mapping
from typing import Any

from .issues import Issue


OUTCOMES: tuple[str, ...] = ('ok', 'warning', 'error', 'undefined')

DEFAULT_TIMEOUT = 30.0
MAX_OUTPUT_BYTES = 4000

_PLACEHOLDER = re.compile(r'\{(path|slug|collection|fields\.[A-Za-z0-9_]+)\}')
_SAFE_VALUE = re.compile(r'[A-Za-z0-9._:-]+')
_KEYS = {'name', 'argv', 'exit_map', 'timeout', 'unavailable', 'blocking'}


@dataclasses.dataclass(frozen=True, eq=False)
class Validator:
  """One external validator.

  Attributes:
      name: Short name, used in issue codes (`validator.NAME`).
      argv: Argument list. May use `{path}`, `{slug}`, `{collection}` and
          `{fields.NAME}` placeholders.
      exit_map: Outcome by exit code; codes not listed count as `undefined`.
      timeout: Seconds before the command is stopped (a timeout result).
      unavailable: Outcome when the command can't run at all (not found,
          not executable) or times out.
      blocking: Outcomes that block a write through the REST API (TODO 6.3):
          the file is rolled back and the request fails with 422.

  """

  name: str
  argv: tuple[str, ...]
  exit_map: Mapping[int, str] = dataclasses.field(
    default_factory=lambda: {0: 'ok', 1: 'error'}
  )
  timeout: float = DEFAULT_TIMEOUT
  unavailable: str = 'undefined'
  blocking: tuple[str, ...] = ()

  def __post_init__(self) -> None:
    if not re.fullmatch(r'[a-z0-9_-]+', self.name):
      raise ValueError(f'Bad validator name {self.name!r}')
    argv = self.argv
    if isinstance(argv, str) or not argv:
      raise ValueError(
        f'Validator {self.name!r}: `argv` must be a list of arguments, '
        'not a string (no shell is used)'
      )
    object.__setattr__(self, 'argv', tuple(str(item) for item in argv))
    exit_map = {int(code): outcome for code, outcome in self.exit_map.items()}
    for outcome in exit_map.values():
      if outcome not in OUTCOMES:
        raise ValueError(
          f'Validator {self.name!r}: unknown outcome {outcome!r}. '
          f'Supported: {", ".join(OUTCOMES)}'
        )
    object.__setattr__(self, 'exit_map', exit_map)
    if self.unavailable not in OUTCOMES:
      raise ValueError(
        f'Validator {self.name!r}: `unavailable` must be one of '
        f'{", ".join(OUTCOMES)}'
      )
    if not isinstance(self.timeout, int | float) or self.timeout <= 0:
      raise ValueError(f'Validator {self.name!r}: `timeout` must be positive')
    object.__setattr__(self, 'blocking', tuple(self.blocking))
    for outcome in self.blocking:
      if outcome not in OUTCOMES:
        raise ValueError(
          f'Validator {self.name!r}: unknown blocking outcome {outcome!r}'
        )

  @classmethod
  def from_dict(cls, data: Mapping[str, Any]) -> 'Validator':
    """Build a validator from its configuration entry.

    Raises:
        ValueError: If the entry is wrong.

    """
    if not isinstance(data, Mapping):
      raise ValueError('A validator must be a mapping')
    unknown = sorted(set(data) - _KEYS)
    if unknown:
      raise ValueError(f'Unknown validator option(s): {unknown}')
    if 'name' not in data or 'argv' not in data:
      raise ValueError('A validator needs `name` and `argv`')
    options = {key: data[key] for key in _KEYS & set(data)}
    if 'blocking' in options and isinstance(options['blocking'], str):
      options['blocking'] = [options['blocking']]
    return cls(**options)

  def is_blocking(self, outcome: str) -> bool:
    """Return whether this outcome rolls a write back (TODO 6.3)."""
    return outcome in self.blocking


def _substitute(
  validator: Validator,
  collection_name: str,
  slug: str,
  path: pathlib.Path,
  frontmatter: Mapping[str, Any],
) -> list[str]:
  values = {'path': str(path), 'slug': slug, 'collection': collection_name}
  result = []
  for argument in validator.argv:

    def replace(match: re.Match[str]) -> str:
      key = match.group(1)
      if key == 'path':
        return values[key]
      if key in values:
        text = values[key]
        label = key
      else:
        label = key.removeprefix('fields.')
        raw = frontmatter.get(label)
        if raw is None and frontmatter.get(key) is None:
          raise ValueError(
            f'Placeholder {key!r} of validator {validator.name!r} matches '
            'no frontmatter field'
          )
        text = '' if raw is None else str(raw)
      # A leading hyphen would let a value pass as an option of the command.
      if not _SAFE_VALUE.fullmatch(text) or text.startswith('-'):
        raise ValueError(
          f'Value of {label!r} is not allowed in a command (use letters, '
          "digits and `._:-`, and don't start with a hyphen)"
        )
      return text

    result.append(_PLACEHOLDER.sub(replace, argument))
  return result


def _environment() -> dict[str, str]:
  env = {'LC_ALL': 'C.UTF-8'}
  if 'PATH' in os.environ:
    env['PATH'] = os.environ['PATH']
  return env


def _trim(data: bytes) -> str:
  text = data[:MAX_OUTPUT_BYTES].decode('utf-8', 'replace').strip()
  if len(data) > MAX_OUTPUT_BYTES:
    text += ' [output truncated]'
  return text


def run_validator(
  validator: Validator,
  *,
  collection_name: str,
  slug: str,
  path: pathlib.Path,
  frontmatter: Mapping[str, Any],
  cwd: pathlib.Path | None = None,
) -> list[Issue]:
  """Run one validator on one document.

  Returns:
      No issues when the outcome is `ok`, otherwise one issue.

  """
  code = f'validator.{validator.name}'
  try:
    argv = _substitute(validator, collection_name, slug, path, frontmatter)
  except ValueError as exc:
    return [Issue('error', f'{code}.unsafe_value', str(exc), slug)]
  try:
    done = subprocess.run(  # noqa: S603 - argument list, no shell
      argv,
      capture_output=True,
      timeout=validator.timeout,
      env=_environment(),
      cwd=str(cwd) if cwd is not None else None,
      stdin=subprocess.DEVNULL,
      check=False,
    )
  except FileNotFoundError:
    return [
      Issue(
        validator.unavailable,
        f'{code}.unavailable',
        f'Validator {validator.name!r} could not run: {argv[0]!r} not found',
        slug,
      )
    ]
  except subprocess.TimeoutExpired:
    return [
      Issue(
        validator.unavailable,
        f'{code}.timeout',
        f'Validator {validator.name!r} did not finish in {validator.timeout}s',
        slug,
      )
    ]
  except OSError as exc:
    return [
      Issue(
        validator.unavailable,
        f'{code}.unavailable',
        f'Validator {validator.name!r} could not run: {exc.strerror or exc}',
        slug,
      )
    ]
  outcome = validator.exit_map.get(done.returncode, 'undefined')
  if outcome == 'ok':
    return []
  output = _trim(done.stdout + done.stderr)
  message = f'Validator {validator.name!r} exited with {done.returncode}'
  if output:
    message += f': {output}'
  return [Issue(outcome, code, message, slug)]


def run_blocking(
  validators: tuple[Validator, ...],
  *,
  collection_name: str,
  slug: str,
  path: pathlib.Path,
  frontmatter: Mapping[str, Any],
  cwd: pathlib.Path | None = None,
) -> list[Issue]:
  """Run every validator and return the findings that block the write."""
  blocking: list[Issue] = []
  for validator in validators:
    for issue in run_validator(
      validator,
      collection_name=collection_name,
      slug=slug,
      path=path,
      frontmatter=frontmatter,
      cwd=cwd,
    ):
      if validator.is_blocking(issue.level):
        blocking.append(issue)
  return blocking

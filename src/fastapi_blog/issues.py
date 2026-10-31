"""The finding type shared by `check` and (later) the validators.

Levels (TODO 6.1): `error` and `warning` are findings; `undefined` means
"could not be checked" and is never treated as fine (П4). A finding always
wins over `undefined` in exit codes.
"""

import dataclasses
from typing import Any


LEVELS: tuple[str, ...] = ('error', 'warning', 'undefined')


@dataclasses.dataclass(frozen=True)
class Issue:
  """One finding of a check or of a validator.

  Attributes:
      level: `error`, `warning` or `undefined`.
      code: Stable machine-readable code such as `schema.invalid`.
      message: What is wrong, in words.
      slug: The document it is about (`None` for the whole collection).
      field: The key it is about, if any.

  """

  level: str
  code: str
  message: str
  slug: str | None = None
  field: str | None = None

  def __post_init__(self) -> None:
    if self.level not in LEVELS:
      raise ValueError(f'Unknown issue level {self.level!r}')

  def to_dict(self) -> dict[str, Any]:
    """Return the issue as a plain dict (for `--json` and HTTP bodies)."""
    return {
      'level': self.level,
      'code': self.code,
      'slug': self.slug,
      'field': self.field,
      'message': self.message,
    }

  def sort_key(self) -> tuple[str, int, str, str, str]:
    """Return the key that orders issues: document, level, code, field."""
    return (
      self.slug or '',
      LEVELS.index(self.level),
      self.code,
      self.field or '',
      self.message,
    )

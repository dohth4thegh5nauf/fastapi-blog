"""Invariance check: forbidden names must not appear in project text files.

Reads the forbidden word list from `forbidden_names.txt` next to this test
(one entry per line, `#` comments and blank lines ignored) and fails if any
entry appears in `src/`, `tests/`, `README.md`, `docs/` or the templates
(they live under `src/fastapi_blog/templates/`). The owner maintains the
list; while it is empty this test skips, because "nothing to check" must
not look like "checked and clean".
"""

import pathlib

import pytest


_ROOT = pathlib.Path(__file__).resolve().parent.parent
_WORDS_FILE = pathlib.Path(__file__).with_name('forbidden_names.txt')

# Text files only; binary artifacts and caches never participate.
_SUFFIXES = {'.py', '.md', '.html', '.txt', '.yaml', '.yml', '.json'}

# The list file itself contains the words by definition. The `posts/` and
# `pages/` directories under `tests/examples/` hold sample blog content,
# not project code — the same exclusion `ruff.toml` applies to them.
_EXCLUDED_NAMES = {'forbidden_names.txt'}
_EXCLUDED_DIRS = {'__pycache__', 'posts', 'pages'}


def _forbidden_words() -> list[str]:
  words = []
  for line in _WORDS_FILE.read_text(encoding='utf-8').splitlines():
    entry = line.strip()
    if entry and not entry.startswith('#'):
      words.append(entry.lower())
  return words


def _candidate_files() -> list[pathlib.Path]:
  files: list[pathlib.Path] = []
  for dirname in ('src', 'tests', 'docs'):
    for path in (_ROOT / dirname).rglob('*'):
      if (
        path.is_file()
        and path.suffix in _SUFFIXES
        and path.name not in _EXCLUDED_NAMES
        and not _EXCLUDED_DIRS & set(path.parts)
      ):
        files.append(path)
  files.append(_ROOT / 'README.md')
  return files


def test_no_forbidden_names() -> None:
  words = _forbidden_words()
  if not words:
    pytest.skip('forbidden_names.txt is empty')
  hits = []
  for path in _candidate_files():
    text = path.read_text(encoding='utf-8', errors='ignore').lower()
    for word in words:
      if word in text:
        hits.append(f'{path.relative_to(_ROOT)}: {word}')
  assert not hits, 'Forbidden names found:\n' + '\n'.join(hits)

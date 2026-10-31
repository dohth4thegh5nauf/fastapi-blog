"""Tests for external validators (TODO 6.2) and checked writes (TODO 6.3)."""

import pathlib
import sys

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import fastapi_blog
from fastapi_blog import validators
from fastapi_blog.validators import Validator


_FAIL = [sys.executable, '-c', 'import sys; sys.exit(1)']
_OK = [sys.executable, '-c', 'import sys; sys.exit(0)']
_ECHO_ARGS = [
  sys.executable,
  '-c',
  'import sys; print(sys.argv[1:]); sys.exit(1)',
]


def test_validator_from_dict_and_defaults():
  validator = Validator.from_dict({'name': 'lint', 'argv': ['true']})
  assert validator.name == 'lint'
  assert validator.exit_map[0] == 'ok'
  assert validator.exit_map[1] == 'error'
  assert validator.unavailable == 'undefined'
  assert validator.blocking == ()


def test_validator_from_dict_reads_all_options():
  validator = Validator.from_dict(
    {
      'name': 'lint',
      'argv': ['markdownlint'],
      'exit_map': {0: 'ok', 1: 'error', 2: 'undefined'},
      'timeout': 20,
      'unavailable': 'warning',
      'blocking': ['error', 'undefined'],
    }
  )
  assert validator.timeout == 20
  assert validator.unavailable == 'warning'
  assert validator.blocking == ('error', 'undefined')
  assert validator.is_blocking('error')
  assert not validator.is_blocking('warning')


@pytest.mark.parametrize(
  'entry',
  [
    'not-a-mapping',
    {'argv': ['true']},
    {'name': 'lint'},
    {'name': 'Bad Name', 'argv': ['true']},
    {'name': 'lint', 'argv': 'markdownlint'},
    {'name': 'lint', 'argv': []},
    {'name': 'lint', 'argv': ['true'], 'bogus': 1},
    {'name': 'lint', 'argv': ['true'], 'exit_map': {0: 'fine'}},
    {'name': 'lint', 'argv': ['true'], 'unavailable': 'nope'},
    {'name': 'lint', 'argv': ['true'], 'blocking': ['nope']},
  ],
)
def test_validator_from_dict_rejects_bad_entries(entry):
  with pytest.raises(ValueError):
    Validator.from_dict(entry)


def test_substitution_uses_slug_collection_and_fields():
  validator = Validator(
    name='lint',
    argv=[
      sys.executable,
      '-c',
      'import sys; print(sys.argv[1:]); sys.exit(1)',
      '{slug}',
      '{collection}',
      '{fields.title}',
    ],
  )
  issues = validators.run_validator(
    validator,
    collection_name='notes',
    slug='a-post',
    path='posts/a-post.md',
    frontmatter={'title': 'Hello'},
    cwd=None,
  )
  assert len(issues) == 1
  assert "['a-post', 'notes', 'Hello']" in issues[0].message


@pytest.mark.parametrize('bad_value', ['a;rm', '-rf', 'has space', 'x/y'])
def test_unsafe_placeholder_value_blocks_the_command(bad_value):
  """A value outside the safe set must not reach the command line."""
  validator = Validator(name='lint', argv=['tool', '{fields.title}'])
  issues = validators.run_validator(
    validator,
    collection_name='notes',
    slug='a',
    path='posts/a.md',
    frontmatter={'title': bad_value},
    cwd=None,
  )
  assert len(issues) == 1
  assert issues[0].code == 'validator.lint.unsafe_value'
  assert issues[0].level == 'error'
  assert bad_value not in issues[0].message or 'not allowed' in (
    issues[0].message
  )


def test_unknown_placeholder_field_is_an_error():
  validator = Validator(name='lint', argv=['tool', '{fields.nope}'])
  issues = validators.run_validator(
    validator,
    collection_name='notes',
    slug='a',
    path='posts/a.md',
    frontmatter={'title': 'Hi'},
    cwd=None,
  )
  assert issues[0].code == 'validator.lint.unsafe_value'


def test_exit_codes_map_to_outcomes():
  validator = Validator(
    name='lint',
    argv=[sys.executable, '-c', 'import sys; sys.exit(2)'],
    exit_map={0: 'ok', 2: 'warning'},
  )
  issues = validators.run_validator(
    validator,
    collection_name='notes',
    slug='a',
    path='posts/a.md',
    frontmatter={},
    cwd=None,
  )
  assert [(issue.level, issue.code) for issue in issues] == [
    ('warning', 'validator.lint')
  ]
  # An unmapped exit code is undefined, never "ok".
  validator = Validator.from_dict({'name': 'lint', 'argv': _FAIL})
  issues = validators.run_validator(
    validator,
    collection_name='notes',
    slug='a',
    path='posts/a.md',
    frontmatter={},
    cwd=None,
  )
  assert issues[0].level == 'error'  # default map: 1 -> error


def test_ok_outcome_reports_nothing():
  validator = Validator.from_dict({'name': 'lint', 'argv': _OK})
  assert (
    validators.run_validator(
      validator,
      collection_name='notes',
      slug='a',
      path='posts/a.md',
      frontmatter={},
      cwd=None,
    )
    == []
  )


def test_missing_command_is_unavailable():
  validator = Validator.from_dict(
    {'name': 'lint', 'argv': ['no-such-validator-command']}
  )
  issues = validators.run_validator(
    validator,
    collection_name='notes',
    slug='a',
    path='posts/a.md',
    frontmatter={},
    cwd=None,
  )
  assert [(issue.level, issue.code) for issue in issues] == [
    ('undefined', 'validator.lint.unavailable')
  ]


def test_timeout_is_unavailable():
  validator = Validator.from_dict(
    {
      'name': 'slow',
      'argv': [sys.executable, '-c', 'import time; time.sleep(5)'],
      'timeout': 0.2,
    }
  )
  issues = validators.run_validator(
    validator,
    collection_name='notes',
    slug='a',
    path='posts/a.md',
    frontmatter={},
    cwd=None,
  )
  assert [(issue.level, issue.code) for issue in issues] == [
    ('undefined', 'validator.slow.timeout')
  ]


def test_run_blocking_keeps_only_blocking_outcomes():
  validator = Validator.from_dict(
    {'name': 'lint', 'argv': _FAIL, 'blocking': ['error']}
  )
  issues = validators.run_blocking(
    (validator,),
    collection_name='notes',
    slug='a',
    path='posts/a.md',
    frontmatter={},
    cwd=None,
  )
  assert len(issues) == 1
  # Without `blocking`, the same failure doesn't block.
  loose = Validator.from_dict({'name': 'lint', 'argv': _FAIL})
  assert (
    validators.run_blocking(
      (loose,),
      collection_name='notes',
      slug='a',
      path='posts/a.md',
      frontmatter={},
      cwd=None,
    )
    == []
  )


@pytest.fixture
def checked_client(tmp_path, monkeypatch):
  monkeypatch.chdir(tmp_path)
  (tmp_path / 'posts').mkdir()

  def build(argv):
    app = FastAPI()
    fastapi_blog.add_blog_to_fastapi(
      app,
      include_api=True,
      api_require_auth=False,
      validators=(
        Validator.from_dict(
          {'name': 'gate', 'argv': argv, 'blocking': ['error']}
        ),
      ),
    )
    return TestClient(app)

  yield build
  fastapi_blog.helpers.clear_posts_cache()


def test_blocking_validator_rolls_back_a_create(tmp_path, checked_client):
  client = checked_client(_FAIL)
  response = client.post(
    '/api/posts/create/note',
    json={
      'frontmatter': {'title': 'N', 'date': '2024-01-01'},
      'content': 'Body',
    },
  )
  assert response.status_code == 422
  assert response.json()['detail']['issues']
  assert not (tmp_path / 'posts' / 'note.md').exists()


def test_blocking_validator_restores_previous_bytes_on_update(
  tmp_path, checked_client
):
  original = (
    '---\ntitle: Old\n# a hand-written comment\ndate: "2024-01-01"\n---\nBody\n'
  )
  (tmp_path / 'posts' / 'note.md').write_text(original, encoding='utf-8')
  client = checked_client(_FAIL)
  response = client.put(
    '/api/posts/update/note',
    json={
      'frontmatter': {'title': 'New', 'date': '2024-01-01'},
      'content': 'Body',
    },
  )
  assert response.status_code == 422
  assert (tmp_path / 'posts' / 'note.md').read_text(encoding='utf-8') == (
    original
  )


def test_blocking_validator_rolls_back_a_save(tmp_path, checked_client):
  (tmp_path / 'posts' / 'old.md').write_text(
    '---\ntitle: Old\n---\nBody\n', encoding='utf-8'
  )
  client = checked_client(_FAIL)
  response = client.post(
    '/api/posts/save',
    json={
      'slug': 'old',
      'frontmatter': {'title': 'New', 'date': '2024-01-01'},
      'content': 'Body',
    },
  )
  assert response.status_code == 422
  assert (tmp_path / 'posts' / 'old.md').read_text(encoding='utf-8') == (
    '---\ntitle: Old\n---\nBody\n'
  )
  # A blocked create through /save removes the new file again.
  response = client.post(
    '/api/posts/save',
    json={
      'slug': 'new',
      'frontmatter': {'title': 'N', 'date': '2024-01-01'},
      'content': 'B',
    },
  )
  assert response.status_code == 422
  assert not (tmp_path / 'posts' / 'new.md').exists()


def test_ok_validator_lets_writes_through(tmp_path, checked_client):
  client = checked_client(_OK)
  response = client.post(
    '/api/posts/create/note',
    json={
      'frontmatter': {'title': 'N', 'date': '2024-01-01'},
      'content': 'Body',
    },
  )
  assert response.status_code == 201
  assert (tmp_path / 'posts' / 'note.md').exists()



def test_validator_uses_shared_template_filters():
  validator = Validator(
    name='example',
    argv=('tool', '--status={fields.status|lower}', '{slug|truncate(8)}'),
  )
  assert validators._substitute(
    validator,
    'posts',
    'Some-Slug',
    pathlib.Path('posts/some.md'),
    {'status': 'PUBLISHED'},
  ) == ['tool', '--status=published', 'Some-Slu']

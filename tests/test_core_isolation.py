"""The core install must work without the optional extras (phase A)."""

import pathlib
import subprocess
import sys
import textwrap
import tomllib

import pytest

import fastapi_blog


ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = pathlib.Path(fastapi_blog.__file__).resolve().parent.parent

# Packages that only the `admin` extra may bring in
BLOCKED = ('starlette_admin', 'sqlalchemy', 'aiosqlite', 'redis')


def _run(script: str, tmp_path: pathlib.Path) -> subprocess.CompletedProcess:
  return subprocess.run(
    [sys.executable, '-c', textwrap.dedent(script)],
    cwd=tmp_path,
    env={'PYTHONPATH': str(SRC), 'PATH': ''},
    capture_output=True,
    text=True,
    timeout=120,
  )


def test_core_imports_without_extras(tmp_path):
  """Importing and running the blog works when every extra is unimportable."""
  result = _run(
    f"""
    import importlib.abc
    import sys

    BLOCKED = {BLOCKED!r}


    class Block(importlib.abc.MetaPathFinder):
      def find_spec(self, name, path, target=None):
        if name.split('.')[0] in BLOCKED:
          raise ModuleNotFoundError(f'blocked: {{name}}', name=name)


    sys.meta_path.insert(0, Block())

    import fastapi_blog
    from fastapi import FastAPI

    app = FastAPI()
    fastapi_blog.add_blog_to_fastapi(app)
    fastapi_blog.setup_fastapi_blog(FastAPI(), admin=False)

    loaded = sorted(m for m in sys.modules if m.split('.')[0] in BLOCKED)
    assert not loaded, loaded
    assert 'fastapi_blog.admin' not in sys.modules

    # The admin names explain which extra is missing
    for name in ('Admin', 'add_admin_to_app'):
      try:
        getattr(fastapi_blog, name)
      except ImportError as exc:
        assert 'fastapi-blog[admin]' in str(exc), exc
      else:
        raise AssertionError(name + ' was importable')

    # The facade asks for the admin by default and fails early
    try:
      fastapi_blog.setup_fastapi_blog(FastAPI())
    except ImportError as exc:
      assert 'fastapi-blog[admin]' in str(exc), exc
    else:
      raise AssertionError('setup_fastapi_blog needs the admin extra')
    print('ok')
    """,
    tmp_path,
  )
  assert result.returncode == 0, result.stderr
  assert result.stdout.strip() == 'ok'


def test_import_does_not_load_the_admin(tmp_path):
  """`import fastapi_blog` doesn't import the admin, even when installed."""
  result = _run(
    """
    import sys

    import fastapi_blog

    assert 'fastapi_blog.admin' not in sys.modules
    assert 'starlette_admin' not in sys.modules
    assert 'sqlalchemy' not in sys.modules
    print('ok')
    """,
    tmp_path,
  )
  assert result.returncode == 0, result.stderr


def test_admin_names_resolve_with_the_extra():
  pytest.importorskip('starlette_admin')
  assert callable(fastapi_blog.add_admin_to_app)
  assert fastapi_blog.Admin is not None
  assert 'add_admin_to_app' in dir(fastapi_blog)


def test_unknown_attribute_is_an_attribute_error():
  with pytest.raises(AttributeError):
    fastapi_blog.no_such_name  # noqa: B018


def test_removed_dependencies_are_gone():
  """No cache server or JWT library is required or mentioned (3.1)."""
  words = ('redis', 'jwt')
  for path in [
    ROOT / 'pyproject.toml',
    *sorted((SRC / 'fastapi_blog').rglob('*.py')),
  ]:
    text = path.read_text(encoding='utf-8').lower()
    for word in words:
      assert word not in text, f'{word!r} found in {path.relative_to(ROOT)}'


def test_extras_are_declared():
  project = tomllib.loads((ROOT / 'pyproject.toml').read_text('utf-8'))[
    'project'
  ]
  core = ' '.join(project['dependencies']).lower()
  for name in ('starlette-admin', 'sqlalchemy', 'aiosqlite'):
    assert name not in core
  extras = project['optional-dependencies']
  assert set(extras) >= {'admin', 'jsonld', 'dev'}
  assert any(x.startswith('starlette-admin') for x in extras['admin'])
  assert any(x.startswith('pyld') for x in extras['jsonld'])


def test_version_matches_pyproject():
  project = tomllib.loads((ROOT / 'pyproject.toml').read_text('utf-8'))[
    'project'
  ]
  assert fastapi_blog.__version__ == project['version']

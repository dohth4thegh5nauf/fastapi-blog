"""`list_posts` follows the files on disk without a restart (phase A, 3.4)."""

import os
import threading

import pytest

from fastapi_blog import helpers


def _post(title: str, body: str = 'text') -> str:
  return (
    f"---\ntitle: {title}\ndate: '2026-01-01'\npublished: true\n---\n{body}\n"
  )


@pytest.fixture
def posts_dir(tmp_path, monkeypatch):
  directory = tmp_path / 'posts'
  directory.mkdir()
  monkeypatch.chdir(tmp_path)
  helpers.list_posts.cache_clear()
  yield directory
  helpers.list_posts.cache_clear()


def _titles() -> list[str]:
  return sorted(x['title'] for x in helpers.list_posts())


def test_external_edit_is_visible(posts_dir):
  (posts_dir / 'a.md').write_text(_post('First'), encoding='utf-8')
  assert _titles() == ['First']
  # Different size: the signature changes even if the mtime doesn't
  (posts_dir / 'a.md').write_text(_post('First, edited'), encoding='utf-8')
  assert _titles() == ['First, edited']


def test_same_size_edit_is_visible_through_mtime(posts_dir):
  path = posts_dir / 'a.md'
  path.write_text(_post('AAAA'), encoding='utf-8')
  assert _titles() == ['AAAA']
  before = path.stat()
  path.write_text(_post('BBBB'), encoding='utf-8')
  # Force a distinct mtime: some file systems have a coarse clock
  os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns + 5_000_000))
  assert _titles() == ['BBBB']


def test_added_and_removed_files_are_visible(posts_dir):
  (posts_dir / 'a.md').write_text(_post('First'), encoding='utf-8')
  assert _titles() == ['First']
  (posts_dir / 'b.md').write_text(_post('Second'), encoding='utf-8')
  assert _titles() == ['First', 'Second']
  (posts_dir / 'a.md').unlink()
  assert _titles() == ['Second']


def test_unchanged_directory_reuses_the_result(posts_dir):
  (posts_dir / 'a.md').write_text(_post('First'), encoding='utf-8')
  first = helpers.list_posts()
  assert helpers.list_posts() is first


def test_missing_directory_is_not_created(tmp_path, monkeypatch):
  monkeypatch.chdir(tmp_path)
  helpers.list_posts.cache_clear()
  assert helpers.list_posts() == ()
  assert not (tmp_path / 'posts').exists()


def test_different_working_directories_do_not_mix(tmp_path, monkeypatch):
  for name in ('one', 'two'):
    (tmp_path / name / 'posts').mkdir(parents=True)
    (tmp_path / name / 'posts' / 'a.md').write_text(
      _post(name), encoding='utf-8'
    )
  helpers.list_posts.cache_clear()
  monkeypatch.chdir(tmp_path / 'one')
  assert _titles() == ['one']
  monkeypatch.chdir(tmp_path / 'two')
  assert _titles() == ['two']


def test_concurrent_readers_and_writer(posts_dir):
  (posts_dir / 'a.md').write_text(_post('First'), encoding='utf-8')
  errors: list[BaseException] = []

  def read():
    try:
      for _ in range(50):
        assert len(helpers.list_posts()) >= 1
    except BaseException as exc:  # noqa: BLE001
      errors.append(exc)

  def write():
    try:
      for i in range(20):
        (posts_dir / f'w{i}.md').write_text(_post(f'W{i}'), encoding='utf-8')
    except BaseException as exc:  # noqa: BLE001
      errors.append(exc)

  threads = [threading.Thread(target=read) for _ in range(4)]
  threads.append(threading.Thread(target=write))
  for thread in threads:
    thread.start()
  for thread in threads:
    thread.join()
  assert not errors
  assert len(helpers.list_posts()) == 21

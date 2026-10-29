"""ModelView pages (Role/User list, detail, edit, create) must render rows.

Regression test for a gap the rest of the suite didn't catch: after the
starlette-admin 1.0 upgrade, `list.html`/`detail.html`/`edit.html`/
`create.html` kept referencing assets (DataTables, a `model` JS object) that
no longer exist in the package. The pages returned 200 but the table was
empty and non-interactive — no test here ever rendered the page body, so
nothing failed. Found via a manual Chrome walkthrough; see `test_admin_theme.py`
for why these 4 pages don't use the project's custom dark theme.
"""

import re

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import fastapi_blog


@pytest.fixture
def client():
  app = FastAPI()
  fastapi_blog.add_admin_to_app(
    app,
    admin_username='admin',
    admin_password='Secret123!',
    secret_key='x' * 64,
    database_url='sqlite+aiosqlite:///:memory:',
    locales=['en'],
    default_locale='en',
  )
  with TestClient(app) as c:
    login_page = c.get('/admin/login')
    token = re.search(
      r'name="csrftoken" value="([^"]+)"', login_page.text
    ).group(1)
    response = c.post(
      '/admin/login',
      data={
        'username': 'admin',
        'password': 'Secret123!',
        'csrftoken': token,
      },
    )
    assert response.status_code == 200  # followed the post-login redirect
    yield c


def test_user_list_page_renders_the_table_shell(client):
  response = client.get('/admin/user/list')
  assert response.status_code == 200
  # The removed DataTables assets must not be referenced any more
  assert 'dt.min.css' not in response.text
  assert 'dt.min.js' not in response.text
  # The new list page's own init call must be present
  assert 'initListPage' in response.text


def test_create_then_list_then_detail_then_edit(client):
  create_page = client.get('/admin/user/create')
  assert create_page.status_code == 200
  token = re.search(
    r'name="csrftoken" value="([^"]+)"', create_page.text
  ).group(1)

  created = client.post(
    '/admin/user/create',
    data={
      'email': 'reader@example.org',
      'hashed_password': 'not-a-real-hash',
      'csrftoken': token,
    },
  )
  assert created.status_code == 200

  listing = client.get('/admin/user/list')
  assert 'reader@example.org' in listing.text

  detail = client.get('/admin/user/detail', params={'pk': 1})
  assert detail.status_code == 200
  assert 'reader@example.org' in detail.text

  edit_page = client.get('/admin/user/edit', params={'pk': 1})
  assert edit_page.status_code == 200
  assert 'reader@example.org' in edit_page.text

"""Search and shared toolbar behavior on the file-backed Posts list."""

import asyncio
import re

import pytest
from fastapi import FastAPI
from httpx2 import ASGITransport, AsyncClient

import fastapi_blog

from tests.auth_helpers import DemoTestAuthProvider


@pytest.mark.parametrize(
  'query, expected_title',
  [
    ('needle', 'Alpha Needle'),
    ('alpha-entry', 'Alpha Needle'),
    ('decisions', 'Alpha Needle'),
  ],
)
def test_posts_search_filters_visible_fields(tmp_path, query, expected_title):
  posts_dir = tmp_path / 'posts'
  posts_dir.mkdir()
  (posts_dir / 'alpha-entry.md').write_text(
    '---\ntitle: Alpha Needle\ntags: [decisions]\n---\nAlpha body\n',
    encoding='utf-8',
  )
  (posts_dir / 'beta-entry.md').write_text(
    '---\ntitle: Beta Record\ntags: [operations]\n---\nBeta body\n',
    encoding='utf-8',
  )

  app = FastAPI()
  fastapi_blog.add_admin_to_app(
    app,
    secret_key='s' * 64,
    database_url='sqlite+aiosqlite:///:memory:',
    posts_dirname=str(posts_dir),
    locales=['en', 'ru'],
    default_locale='en',
    auth_provider=lambda locale: DemoTestAuthProvider(),
  )

  async def request_posts_list():
    try:
      async with AsyncClient(
        transport=ASGITransport(app=app), base_url='http://test'
      ) as client:
        login_page = await client.get('/admin/login')
        token = re.search(
          r'name="csrftoken" value="([^"]+)"', login_page.text
        ).group(1)
        login = await client.post(
          '/admin/login',
          data={
            'username': 'admin',
            'password': 'Secret123!',
            'csrftoken': token,
          },
        )
        assert login.status_code == 303

        response = await client.get('/admin/posts', params={'q': query})

        assert response.status_code == 200
        assert expected_title in response.text
        assert 'Beta Record' not in response.text
        assert f'name="q" value="{query}"' in response.text
        assert (
          'class="card-title d-flex align-items-center gap-3"' in response.text
        )
        assert 'class="btn-list post-row-actions"' in response.text
    finally:
      await app.state.admin_engine.dispose()

  asyncio.run(request_posts_list())

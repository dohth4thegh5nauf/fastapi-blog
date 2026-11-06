"""Example: Admin panel with internationalization (i18n).

Demonstrates how to use the i18n feature with English and Russian locales.
"""

from demo_auth import (
  DEMO_DATABASE_URL,
  create_demo_auth_provider,
  install_demo_auth,
)
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

import fastapi_blog


app = FastAPI(title='Multilingual Blog Admin')

# Add blog with i18n support
fastapi_blog.add_blog_to_fastapi(
  app,
  prefix='blog',
  strict_frontmatter=False,
  sanitize_html=False,
  locales=['en', 'ru'],  # Enable language switcher
  default_locale='en',
)

# Add admin panel with Russian as default language
admin = fastapi_blog.add_admin_to_app(
  app,
  title='Админ-панель блога',  # Russian title
  database_url=DEMO_DATABASE_URL,
  secret_key='demo-only-session-secret-0123456789abcdef0123456789',
  auth_provider=lambda locale: create_demo_auth_provider(locale),
  locales=['en', 'ru'],
  default_locale='en',
)
install_demo_auth(app)

app.mount('/static', StaticFiles(directory='static'), name='static')


@app.get('/')
async def index() -> dict:
  return {
    'message': 'Multilingual admin panel example',
    'blog': 'http://localhost:8000/blog',
    'admin_en': 'http://localhost:8000/admin (switch to English in UI)',
    'admin_ru': 'http://localhost:8000/ru/admin',
    'demo_credentials': {'username': 'admin', 'password': 'Admin123!'},
    'note': 'Open /ru/admin for the Russian interface.',
  }

"""Example: Admin panel with internationalization (i18n).

Demonstrates how to use the i18n feature with English and Russian locales.
"""

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

import fastapi_blog


app = FastAPI(title="Multilingual Blog Admin")

# Add blog with i18n support
fastapi_blog.add_blog_to_fastapi(
    app,
    prefix="blog",
    strict_frontmatter=False,
    sanitize_html=False,
    locales=["en", "ru"],  # Enable language switcher
    default_locale="en",
)

# Add admin panel with Russian as default language
admin = fastapi_blog.add_admin_to_app(
    app,
    title="Админ-панель блога",  # Russian title
    base_url="/admin",
    admin_username="admin",
    admin_password="Admin123!",
    secret_key="change-me-in-production",
    i18n_enabled=True,
    i18n_default_locale="en",  # English by default
    i18n_locales=["en", "ru"],  # Language switcher with EN/RU
)

app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
async def index() -> dict:
    return {
        "message": "Multilingual admin panel example",
        "blog": "http://localhost:8000/blog",
        "admin_en": "http://localhost:8000/admin (switch to English in UI)",
        "admin_ru": "http://localhost:8000/admin (по умолчанию русский)",
        "credentials": {"username": "admin", "password": "Admin123!"},
        "note": "Language can be switched in the admin interface",
    }

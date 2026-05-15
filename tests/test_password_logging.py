"""Test that passwords are not logged at INFO level."""

import logging

from fastapi import FastAPI

import fastapi_blog


def test_password_not_logged_at_info(caplog):
    """Verify that password is not logged at INFO level."""
    app = FastAPI()

    with caplog.at_level(logging.INFO, logger="fastapi_blog.admin"):
        fastapi_blog.add_admin_to_app(
            app,
            admin_username="admin",
            admin_password="SuperSecret123!",
            secret_key="test-secret-key",
            database_url="sqlite+aiosqlite:///:memory:",
            locales=["en"],
            default_locale="en",
        )

    # Password should NOT appear in INFO logs
    assert "SuperSecret123!" not in caplog.text
    assert "password=" not in caplog.text.lower() or "password='***'" in caplog.text


def test_password_logged_at_debug(caplog):
    """Verify that username (not password) is logged at DEBUG level."""
    app = FastAPI()

    with caplog.at_level(logging.DEBUG, logger="fastapi_blog.admin"):
        fastapi_blog.add_admin_to_app(
            app,
            admin_username="admin",
            admin_password="SuperSecret123!",
            secret_key="test-secret-key",
            database_url="sqlite+aiosqlite:///:memory:",
            locales=["en"],
            default_locale="en",
        )

    # Username should appear in DEBUG logs
    assert "username=admin" in caplog.text
    # But password should NOT appear even in DEBUG
    assert "SuperSecret123!" not in caplog.text


def test_logger_info_messages(caplog):
    """Verify that expected INFO messages are logged."""
    app = FastAPI()

    with caplog.at_level(logging.INFO, logger="fastapi_blog.admin"):
        fastapi_blog.add_admin_to_app(
            app,
            admin_username="admin",
            admin_password="test",
            secret_key="test-secret-key",
            database_url="sqlite+aiosqlite:///:memory:",
            locales=["en", "ru"],
            default_locale="en",
        )

    # Check expected INFO messages
    assert "Admin panel (en) mounted at /en/admin" in caplog.text
    assert "Admin panel (ru) mounted at /ru/admin" in caplog.text
    assert "/admin redirects to /en/admin" in caplog.text
    assert "Available locales: en, ru" in caplog.text
    assert "Access at: http://localhost:8000/en/admin" in caplog.text

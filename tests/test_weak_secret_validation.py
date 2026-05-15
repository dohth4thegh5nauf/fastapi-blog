"""Test validation of weak secret_key."""

import warnings

import pytest
from fastapi import FastAPI

import fastapi_blog


def test_weak_secret_key_warns():
    """Verify that weak secret_key generates UserWarning."""
    app = FastAPI()

    with pytest.warns(UserWarning, match="secret_key is weak"):
        fastapi_blog.add_admin_to_app(
            app,
            secret_key="short",
            database_url="sqlite+aiosqlite:///:memory:",
            locales=["en"],
            default_locale="en",
        )


def test_default_secret_key_warns():
    """Verify that default secret_key generates UserWarning."""
    app = FastAPI()

    with pytest.warns(UserWarning, match="secret_key is weak"):
        fastapi_blog.add_admin_to_app(
            app,
            secret_key="change-me-in-production-please-use-strong-secret",
            database_url="sqlite+aiosqlite:///:memory:",
            locales=["en"],
            default_locale="en",
        )


def test_test_secret_key_warns():
    """Verify that test-secret-key generates UserWarning."""
    app = FastAPI()

    with pytest.warns(UserWarning, match="secret_key is weak"):
        fastapi_blog.add_admin_to_app(
            app,
            secret_key="test-secret-key",
            database_url="sqlite+aiosqlite:///:memory:",
            locales=["en"],
            default_locale="en",
        )


def test_strong_secret_key_no_warning():
    """Verify that strong secret_key does not generate warning."""
    app = FastAPI()

    # Generate a strong secret (64 chars)
    strong_secret = "a" * 64

    with warnings.catch_warnings():
        warnings.simplefilter("error")  # Turn warnings into errors
        try:
            fastapi_blog.add_admin_to_app(
                app,
                secret_key=strong_secret,
                database_url="sqlite+aiosqlite:///:memory:",
                locales=["en"],
                default_locale="en",
            )
        except UserWarning:
            pytest.fail("Strong secret_key should not generate warning")


def test_empty_secret_key_warns():
    """Verify that empty secret_key generates UserWarning."""
    app = FastAPI()

    with pytest.warns(UserWarning, match="secret_key is weak"):
        fastapi_blog.add_admin_to_app(
            app,
            secret_key="",
            database_url="sqlite+aiosqlite:///:memory:",
            locales=["en"],
            default_locale="en",
        )


def test_warning_message_includes_example():
    """Verify that warning message includes generation example."""
    app = FastAPI()

    with pytest.warns(UserWarning, match="secrets.token_hex\\(32\\)"):
        fastapi_blog.add_admin_to_app(
            app,
            secret_key="weak",
            database_url="sqlite+aiosqlite:///:memory:",
            locales=["en"],
            default_locale="en",
        )

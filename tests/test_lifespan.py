from contextlib import asynccontextmanager

import pytest
from fastapi import FastAPI
from sqlalchemy import inspect
from starlette.testclient import TestClient

from fastapi_blog.admin import add_admin_to_app


@pytest.mark.anyio
async def test_admin_lifespan_composition():
    """Verify `add_admin_to_app` correctly composes with an existing app lifespan."""
    startup_events = []
    shutdown_events = []

    @asynccontextmanager
    async def custom_lifespan(app: FastAPI):
        # User's startup logic
        startup_events.append("user_startup")
        yield
        # User's shutdown logic
        shutdown_events.append("user_shutdown")

    app = FastAPI(lifespan=custom_lifespan)

    # Add admin to the app. This will add another lifespan for DB init.
    # Use in-memory SQLite database for testing.
    add_admin_to_app(
        app,
        database_url="sqlite+aiosqlite:///:memory:",
        init_database=True,
    )

    # The TestClient context manager will trigger startup and shutdown events.
    with TestClient(app) as client:
        # 1. Verify user's startup logic was called
        assert "user_startup" in startup_events

        # 2. Verify admin's startup logic was called.
        # The admin lifespan initializes the database, so we check if tables exist.
        engine = client.app.state.admin_engine

        # Use async context to inspect the database
        async with engine.connect() as conn:
            result = await conn.run_sync(
                lambda sync_conn: inspect(sync_conn).has_table("users")
            )
            assert result, "Table 'users' should be created by admin lifespan"

            result = await conn.run_sync(
                lambda sync_conn: inspect(sync_conn).has_table("posts")
            )
            assert result, "Table 'posts' should be created by admin lifespan"

    # 3. Verify user's shutdown logic was called
    assert "user_shutdown" in shutdown_events

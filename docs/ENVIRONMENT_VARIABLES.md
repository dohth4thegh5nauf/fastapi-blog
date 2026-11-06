# Environment Variables Configuration

FastAPI Blog reads environment variables for settings that are shared by the
library. Authentication credentials belong to the host application's
`AuthProvider`; the package does not read admin login or password variables.

## Blog configuration

### `FASTAPI_BLOG_INCLUDE_API`

Controls whether REST API endpoints are included when `include_api` is omitted.
Values `true`, `1`, and `yes` enable the API (case-insensitive); other values
disable it. An explicit `include_api` argument takes precedence.

```bash
export FASTAPI_BLOG_INCLUDE_API=true
```

## Admin configuration

### `DATABASE_URL`

Database URL for admin models. Defaults to
`sqlite+aiosqlite:///./data/app.db`.

```bash
export DATABASE_URL='postgresql+asyncpg://user:pass@localhost/blog'
```

### `SECRET_KEY`

Session secret used by the admin panel. It must contain at least 32 characters
and must not be a known placeholder. Generate a key with:

```bash
export SECRET_KEY="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
```

Admin setup also requires a host-supplied Starlette Admin `AuthProvider`; see
[Admin Authentication](ADMIN_AUTHENTICATION.md). `FASTAPI_BLOG_ADMIN_LOGIN`,
`FASTAPI_BLOG_ADMIN_PASSWORD`, and `POSTS_DIR` are not supported configuration
variables. Pass the posts directory explicitly with `posts_dirname`.

## Example

```python
import os

from fastapi import FastAPI

from fastapi_blog import add_admin_to_app
from myapp.auth import create_auth_provider

app = FastAPI()
admins = add_admin_to_app(
  app,
  auth_provider=lambda locale: create_auth_provider(locale),
  secret_key=os.environ['SECRET_KEY'],
  database_url=os.getenv('DATABASE_URL'),
  posts_dirname='posts',
)
```

The REST API uses separate authentication. Configure it with
`admin_username`/`admin_password` or a custom dependency on
`add_blog_to_fastapi()`; these are not admin-panel credentials.

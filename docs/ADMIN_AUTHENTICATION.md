# Admin Authentication Providers

FastAPI Blog adds Starlette Admin's user interface and views. The host
application owns authentication and provides a Starlette Admin
`AuthProvider`. The provider validates identities, manages its session state,
and can attach the host identity to `request.state.blog_user` for the
application's `authorize(request, resource, action)` callback.

## Provide a provider

Install the admin extra and implement Starlette Admin's `AuthProvider` in the
host application. This small example shows the contract; replace its
credential check and session identity with the host application's identity
system:

```python
from starlette.requests import Request
from starlette.responses import Response
from starlette_admin.auth import AdminUser, AuthProvider
from starlette_admin.exceptions import LoginFailed


class HostAuthProvider(AuthProvider):
  async def login(
    self,
    username: str,
    password: str,
    remember_me: bool,
    request: Request,
  ) -> Response | None:
    user = await host_identity_service.authenticate(username, password)
    if user is None:
      raise LoginFailed('Invalid username or password')
    request.session['host_user_id'] = user.id
    return None

  async def authenticate(self, request: Request) -> AdminUser | None:
    user_id = request.session.get('host_user_id')
    if user_id is None:
      return None
    user = await host_identity_service.get_user(user_id)
    if user is None:
      request.session.clear()
      return None
    request.state.blog_user = {
      'username': user.username,
      'role': user.role,
      'is_admin': user.is_admin,
    }
    return AdminUser(username=user.username)

  async def logout(self, request: Request) -> Response | None:
    request.session.clear()
    return None
```

Pass a fresh provider per locale:

```python
import os

from fastapi import FastAPI
from fastapi_blog import add_admin_to_app

app = FastAPI()
admins = add_admin_to_app(
  app,
  auth_provider=lambda locale: HostAuthProvider(),
  secret_key=os.environ['SECRET_KEY'],
  locales=['en', 'ru'],
  default_locale='en',
  authorize=host_authorize,
)
```

The factory is called once for every locale and must return a distinct
`AuthProvider` instance each time. A single provider instance is supported
only when configuring one locale. Starlette Admin attaches event and route
state to each provider, so a shared instance cannot be mounted across
localized Admin objects.

The provider needs the normal Starlette session support. FastAPI Blog installs
`SessionMiddleware` with a strong secret unless an equivalent middleware is
already configured. Starlette Admin continues to protect its login and admin
forms with its built-in CSRF handling; providers should not disable or replace
that protection. `https_only=True` enables secure session cookies for HTTPS.

## Keep responsibilities separate

- `auth_provider` performs login, logout, and request identity lookup.
- `authorize(request, resource, action)` decides whether that identity may
  perform an operation. FastAPI Blog does not infer permissions from a
  provider's account database.
- `configure_admin(locale, admin)` registers views before the localized admin
  is mounted. It does not authenticate users or grant permissions.
- FastAPI Blog's `User`, `UserWithRoles`, and `Role` views are database CRUD
  features. Editing those records does not create, update, or delete accounts
  in a host-supplied provider. The repository's local demo provider is an
  explicit example that authenticates against its own `UserWithRoles` and
  `Role` records.
- The REST API has separate authentication configuration. An Admin provider
  does not authenticate REST API requests. Use the API credentials or
  `api_auth_dependency` accepted by `add_blog_to_fastapi()`; when using
  `setup_fastapi_blog()`, pass `api_auth_dependency` separately.

## Legacy migration

For migration, calls without `auth_provider` continue to use the legacy
`admin_username`, `admin_password`, and `auth_users` path. Those parameters are
mutually exclusive with `auth_provider`; ambiguous combinations fail while
the app is configured. The legacy path still requires a password and strong
session secret (unless the existing local-only `insecure_dev=True` option is
used). New integrations should provide their own provider.

The repository's demo provider lives in `tests/examples/demo_auth.py`. Demo
applications use an isolated in-memory SQLite admin database and seed a
`UserWithRoles` account with the active `admin` role at startup. The local demo
credentials are `admin` / `Admin123!`; the seed is restored at each startup so
the account remains available for walkthroughs. This is demo-only behavior,
not a production account system. A host application should supply its own
`AuthProvider` and user lifecycle.

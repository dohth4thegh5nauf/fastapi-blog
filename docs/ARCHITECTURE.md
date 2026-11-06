# FastAPI Blog - Architecture Overview

## System Architecture

```
┌────────────────────────────────────────────────────────────────┐
│                        FastAPI Application                     │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│  ┌────────────────┐  ┌────────────────┐  ┌────────────────┐    │
│  │  Public Blog   │  │  Admin Panel   │  │   REST API     │    │
│  │   /blog/*      │  │   /admin/*     │  │  /api/posts/*  │    │
│  └────────────────┘  └────────────────┘  └────────────────┘    │
│         │                    │                    │            │
│         │                    │                    │            │
│         ▼                    ▼                    ▼            │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │              Router Layer (FastAPI)                      │  │
│  └──────────────────────────────────────────────────────────┘  │
│         │                    │                    │            │
│         │                    │                    │            │
│         ▼                    ▼                    ▼            │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐         │
│  │   Markdown  │    │  Starlette  │    │   Markdown  │         │
│  │   Renderer  │    │    Admin    │    │    CRUD     │         │
│  └─────────────┘    └─────────────┘    └─────────────┘         │
│         │                    │                    │            │
│         ▼                    ▼                    ▼            │
│  ┌─────────────────────────────────────────────────────┐       │
│  │              Storage Layer                          │       │
│  ├──────────────────────┬──────────────────────────────┤       │
│  │  Markdown Files      │  SQLite/PostgreSQL           │       │
│  │  posts/*.md          │  - users                     │       │
│  │  pages/*.md          │  - posts (optional)          │       │
│  │                      │  - roles                     │       │
│  └──────────────────────┴──────────────────────────────┘       │
│                                                                │
└────────────────────────────────────────────────────────────────┘
```

## Request Flow

### Public Blog Request

```
User Request → FastAPI Router → Blog Router → Markdown Parser
                                    ↓
                            Jinja2 Templates
                                    ↓
                              HTML Response
```

### Admin Panel Request

```
User Request → SessionMiddleware → FastAPI Router → Starlette-Admin
                     ↓                                      ↓
               Auth Check                          ModelView/CustomView
                     ↓                                      ↓
            Database (SQLAlchemy)                    Jinja2 Templates
                                                            ↓
                                                      HTML Response
```

### REST API Request

```
User Request → Auth Middleware → FastAPI Router → Markdown CRUD
                     ↓                                  ↓
               Auth Check                      File Operations
                                                       ↓
                                              JSON Response
```

## Multi-Locale Architecture

### Blog Localization

```
URL Structure:
/blog/           → Default locale (en)
/ru/blog/        → Russian locale
/fr/blog/        → French locale

Accept-Language → Middleware → Locale Detection → Router Selection
```

### Admin Panel Localization

```
Current Implementation (Multi-Instance):
/admin/          → English admin (default)
/ru/admin/       → Russian admin
/fr/admin/       → French admin

Each locale = Separate Admin instance + Auth provider
```

**Problem:** Multiple Admin instances create conflicting login endpoints.

**Alternative Approach:**
```
Single Admin Instance + Session-Based Locale:
/admin/          → All locales
  ↓
Session['locale'] → Translation Selection → UI Language
```

## Data Flow

### Writing a Blog Post

```
Markdown File → YAML Parser → Frontmatter Extraction
     ↓                              ↓
Content Body                  Metadata (title, date, tags)
     ↓                              ↓
Markdown → HTML              Post Object (Pydantic)
     ↓                              ↓
   Jinja2 Template Rendering → HTML Response
```

### Admin User Management

```
Login Form → Auth Provider → Password Verification (bcrypt)
                ↓                      ↓
          Session Store          User Record (SQLAlchemy)
                ↓
          Session Cookie → Subsequent Requests → Auth Check
```

## Component Dependencies

```
fastapi_blog
├── main.py (add_blog_to_fastapi)
│   └── router.py (get_blog_router)
│       ├── helpers.py (markdown parsing)
│       └── templates/ (Jinja2)
│
├── admin/__init__.py (add_admin_to_app)
│   ├── database.py (SQLAlchemy setup)
│   ├── models/ (User, Post, Role, UserWithRoles)
│   ├── views.py, views_role.py (ModelViews)
│   ├── markdown_crud.py (markdown file operations)
│   ├── i18n.py (translations)
│   └── templates/ (custom starlette-admin templates)
│
└── editor.py (add_editor_to_app)
```

## Security Architecture

### Authentication and authorization

Admin login uses the host application's Starlette Admin `AuthProvider`; the
host owns account storage and credential validation. Admin setup requires a
provider and a session secret (`secret_key` or `SECRET_KEY`) of at least 32
characters that is not a known placeholder. There is no package-managed admin
credential store or development login.
`https_only=True` sets the session cookie's `Secure` attribute;
`SameSite=Lax` is the default. If the application already has a
`SessionMiddleware`, it must use the exact same secret and `SameSite=Lax` or
`Strict`; `https_only=True` additionally requires that middleware to set
`https_only=True`. Startup rejects mismatched external session configuration.

A single authorization callback has the shape
`authorize(request, resource, action) -> bool`. It is used by the REST API,
Markdown `CustomView` routes and SQLAlchemy `ModelView` hooks. Without a custom
callback, the policy grants:

| Role | Posts | Users/settings | Role management |
| --- | --- | --- | --- |
| `admin` | create/read/update/delete/publish | full access | full access |
| `editor` | create/read/update/publish | read only | denied |
| `viewer` | read only | denied | denied |

Missing or unknown roles, resources and actions are denied. A session role is
preserved when the session cookie is also used for REST API authentication.
Starlette Admin's built-in CSRF protection continues to guard its own forms.
Cookie-authenticated unsafe requests to REST API paths additionally require
an `Origin` whose scheme and authority exactly match the request scheme and
`Host`; missing, duplicate or malformed Origin/Host headers are rejected. The
guard also rejects protocol-relative and opaque Origins. It is deliberately
not installed on admin paths: Starlette Admin's built-in CSRF middleware
protects its own login, forms and custom-view routes. Basic-auth and other
non-cookie REST requests are not subject to this Origin gate.

Starlette Admin's synchronous `ModelView` hooks accept a synchronous custom
authorizer. REST and Markdown custom routes also accept awaitable callbacks;
ModelView hooks deny an awaitable result rather than treating it as permission.

### Storage and request boundaries

The public blog, REST API and admin Markdown views read the same files through
`DocumentStore` and share the collection configuration and frontmatter
schema. Writes go through `DocumentService` on both boundaries (no loopback
HTTP request from the admin panel): it applies schema validation and
write-time `on_create`/`read_only` rules, checks configured uniqueness and
blocking validators, commits atomically, then emits change events and
invalidates the post cache. The REST API validates request payloads and maps
failures to HTTP status codes before delegating to the same commit path; the
admin form supplies etags and renders the service's diagnostics. The optional
SQL database stores admin accounts and role-management data; it is not a
mirror of Markdown content.

For multi-tenant applications, `CollectionSpec.dir` may be a callable that
accepts the current request and returns an absolute collection path. The
resolved path is memoized on request state, so a request uses one consistent
root across public routes, REST, admin, health probes and SEO endpoints. Static
`Path` values remain supported. Request-resolved roots are an application
runtime feature; project-file CLI commands require static paths.

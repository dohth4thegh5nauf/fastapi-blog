# FastAPI Blog - Architecture Overview

## System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        FastAPI Application                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  ┌────────────────┐  ┌────────────────┐  ┌────────────────┐    │
│  │  Public Blog   │  │  Admin Panel   │  │   REST API     │    │
│  │   /blog/*      │  │   /admin/*     │  │  /api/posts/*  │    │
│  └────────────────┘  └────────────────┘  └────────────────┘    │
│         │                    │                    │              │
│         │                    │                    │              │
│         ▼                    ▼                    ▼              │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │              Router Layer (FastAPI)                       │  │
│  └──────────────────────────────────────────────────────────┘  │
│         │                    │                    │              │
│         │                    │                    │              │
│         ▼                    ▼                    ▼              │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐        │
│  │   Markdown  │    │  Starlette  │    │   Markdown  │        │
│  │   Renderer  │    │    Admin    │    │    CRUD     │        │
│  └─────────────┘    └─────────────┘    └─────────────┘        │
│         │                    │                    │              │
│         ▼                    ▼                    ▼              │
│  ┌─────────────────────────────────────────────────────┐       │
│  │              Storage Layer                           │       │
│  ├──────────────────────┬──────────────────────────────┤       │
│  │  Markdown Files      │  SQLite/PostgreSQL           │       │
│  │  posts/*.md          │  - users                     │       │
│  │  pages/*.md          │  - posts (optional)          │       │
│  │                      │  - roles                     │       │
│  └──────────────────────┴──────────────────────────────┘       │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
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
│   ├── auth_provider.py (SimpleAuthProvider)
│   ├── database.py (SQLAlchemy setup)
│   ├── models.py (User, Post)
│   ├── views.py (ModelViews)
│   ├── i18n.py (translations)
│   └── templates/ (custom starlette-admin templates)
│
└── editor.py (add_editor_to_app)
    └── markdown_crud.py (file operations)
```

## Security Architecture

### Authentication Flow

```
1. User submits login credentials
2. Auth Provider validates against database
3. Session created with signed cookie (itsdangerous)
4. Subsequent requests verify session
5. Logout clears session
```

### Authorization (RBAC)

```
Request → Session → User Object
            ↓
        Role Check → RoleModelView.is_accessible()
            ↓
      Grant/Deny Access
```

## Database Schema

### Users Table

```sql
CREATE TABLE users (
    id INTEGER PRIMARY KEY,
    email VARCHAR(255) UNIQUE NOT NULL,
    hashed_password VARCHAR NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    is_admin BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP,
    updated_at TIMESTAMP
);
```

### Posts Table (Optional)

```sql
CREATE TABLE posts (
    id INTEGER PRIMARY KEY,
    slug VARCHAR(255) UNIQUE NOT NULL,
    title VARCHAR(500) NOT NULL,
    content TEXT,
    description VARCHAR(1000),
    tags JSON,
    published BOOLEAN DEFAULT FALSE,
    publish_date TIMESTAMP,
    created_at TIMESTAMP,
    updated_at TIMESTAMP
);
```

### Roles Table (RBAC)

```sql
CREATE TABLE roles (
    id INTEGER PRIMARY KEY,
    name VARCHAR(100) UNIQUE NOT NULL,
    description VARCHAR(500)
);

CREATE TABLE user_roles (
    user_id INTEGER,
    role_id INTEGER,
    PRIMARY KEY (user_id, role_id),
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (role_id) REFERENCES roles(id)
);
```

## Deployment Architecture

### Development

```
FastAPI (uvicorn) → SQLite → Markdown Files (local)
     ↑
Port 8000 (localhost)
```

### Production

```
              ┌─────────────┐
              │   Nginx     │ (Reverse Proxy)
              └──────┬──────┘
                     │
                     ▼
              ┌─────────────┐
              │   Uvicorn   │ (Multiple workers)
              └──────┬──────┘
                     │
         ┌───────────┴───────────┐
         ▼                       ▼
  ┌─────────────┐        ┌─────────────┐
  │ PostgreSQL  │        │  Markdown   │
  │  Database   │        │   Files     │
  └─────────────┘        └─────────────┘
```

### Docker Deployment

```
Docker Container
├── FastAPI Application
├── SQLite Database (volume mount)
└── Markdown Files (volume mount)
```

## Scaling Considerations

### Horizontal Scaling

**Challenge:** Session storage across multiple instances

**Solution:**
- Redis for shared session store
- JWT tokens instead of sessions
- Database-backed sessions

### Performance Optimization

**Blog:**
- Cache rendered markdown
- Pre-generate static pages
- CDN for static assets

**Admin:**
- Database connection pooling
- Async SQLAlchemy queries
- Pagination for large datasets

---

**See also:**
- [CODEBASE_SUMMARY_RU.md](CODEBASE_SUMMARY_RU.md) - Detailed codebase analysis (Russian)
- [DATABASE.md](DATABASE.md) - Database architecture details
- [ROLE_MANAGEMENT.md](ROLE_MANAGEMENT.md) - RBAC implementation

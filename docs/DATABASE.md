# Database Architecture - FastAPI Blog

## Overview

FastAPI Blog uses **two separate storage systems**:

1. **SQLite/PostgreSQL Database** - for admin panel data (users, auth, optional posts)
2. **Markdown Files** - for blog posts (primary storage)

This hybrid approach provides flexibility: simple file-based posts for the blog, with a robust database for user management.

---

## Database Configuration

### Default Setup

By default, the database is stored at `./data/app.db` (SQLite with async support):

```python
import os
from fastapi import FastAPI
import fastapi_blog
from myapp.auth import create_auth_provider

app = FastAPI()

fastapi_blog.add_admin_to_app(
  app,
  auth_provider=lambda locale: create_auth_provider(locale),
  secret_key=os.environ['SECRET_KEY'],
  # database_url not specified = uses default SQLite
)
```

**Default URL**: `sqlite+aiosqlite:///./data/app.db`

### Custom Database URL

Specify a custom database:

```python
# SQLite in custom location
fastapi_blog.add_admin_to_app(
    app,
    database_url="sqlite+aiosqlite:///./my_blog.db",
    ...
)

# PostgreSQL
fastapi_blog.add_admin_to_app(
    app,
    database_url="postgresql+asyncpg://user:pass@localhost/blog",
    ...
)
```

### Environment Variable

You can also set via environment:

```bash
export DATABASE_URL="postgresql+asyncpg://user:pass@localhost/blog"
```

The code checks `os.getenv("DATABASE_URL")` first before using the default.

---

## Database Models

### User Model

**Table**: `users`

```python
from fastapi_blog.admin.models import User

# Fields:
- id: int (PK, autoincrement)
- email: str (unique, indexed, max 255)
- hashed_password: str (bcrypt hash)
- is_active: bool (default: True)
- is_admin: bool (default: False)
- created_at: datetime (auto)
- updated_at: datetime (auto on update)
```

**Purpose**: Authentication and user management for admin panel.

**Password Hashing**: Uses bcrypt directly (via `fastapi_blog.admin.passwords`) for secure password storage.

### Post Model

**Table**: `posts`

```python
from fastapi_blog.admin.models import Post

# Fields:
- id: int (PK, autoincrement)
- slug: str (unique, indexed, max 255)
- title: str (max 500)
- content: str (text)
- description: str (max 1000, optional)
- tags: list (JSON, optional)
- image: str (max 500, optional)
- published: bool (default: False)
- publish_date: datetime (optional)
- created_at: datetime (auto)
- updated_at: datetime (auto on update)
```

**Purpose**: Optional database-backed posts (alternative to markdown files).

**Note**: By default, FastAPI Blog uses markdown files for posts. The Post model is available if you want database-backed posts instead.

---

## Database Initialization

### Automatic Initialization

By default, the database is initialized automatically when the app starts:

```python
fastapi_blog.add_admin_to_app(
    app,
    init_database=True,  # Default: True
    ...
)
```

This:
1. Creates the database file (if SQLite)
2. Creates all tables (`users`, `posts`)
3. Runs during app lifespan startup

### Manual Initialization

To initialize manually:

```python
from fastapi_blog.admin.database import create_engine_and_session, init_db
import asyncio

engine, session_factory = create_engine_and_session(database_url)
asyncio.run(init_db(engine))
```

### Disable Auto-initialization

```python
fastapi_blog.add_admin_to_app(
    app,
    init_database=False,  # Don't auto-initialize
    ...
)
```

**Use case**: When you want to manage migrations yourself (e.g., with Alembic).

---

## Database Engine

### Async SQLAlchemy

FastAPI Blog uses **async SQLAlchemy 2.0** with asyncio support:

```python
from sqlalchemy.ext.asyncio import create_async_engine

# For SQLite
engine = create_async_engine(
  'sqlite+aiosqlite:///./blog.db',
  echo=True,  # Enable SQL logging
  pool_pre_ping=True,  # Check connection health
)

# For PostgreSQL
engine = create_async_engine(
  'postgresql+asyncpg://user:pass@localhost/blog',
  echo=False,
  pool_pre_ping=True,
)
```

### Session Management

Sessions are managed via `async_sessionmaker`:

```python
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession

AsyncSessionLocal = async_sessionmaker(
  engine,
  class_=AsyncSession,
  expire_on_commit=False,
)

# Usage
async with AsyncSessionLocal() as session:
  # Your queries here
  await session.commit()
```

### Dependency Injection

For custom endpoints:

```python
from fastapi_blog.admin.database import get_db


@app.get('/my-endpoint')
async def my_endpoint(db: AsyncSession = Depends(get_db)):
  result = await db.execute(select(User))
  users = result.scalars().all()
  return users
```

---

## Supported Databases

### SQLite (Default)

**Driver**: `aiosqlite`

```python
"sqlite+aiosqlite:///./blog.db"
```

**Pros**:
- Zero configuration
- File-based (portable)
- Perfect for development/small sites

**Cons**:
- Limited concurrency
- No network access

### PostgreSQL

**Driver**: `asyncpg`

```python
"postgresql+asyncpg://user:password@host:5432/database"
```

**Pros**:
- Production-ready
- High concurrency
- Advanced features (full-text search, JSON, etc.)
- Network access

**Cons**:
- Requires separate server

**Installation**:
```bash
pip install asyncpg
```

### MySQL/MariaDB

**Driver**: `aiomysql`

```python
"mysql+aiomysql://user:password@host:3306/database"
```

**Installation**:
```bash
pip install aiomysql
```

---

## Database vs Markdown Files

### When to Use What?

| Feature | Markdown Files | Database Posts |
|---------|---------------|----------------|
| **Blog posts** | ✅ Default | ⚠️ Alternative |
| **Git-friendly** | ✅ Yes | ❌ No |
| **Version control** | ✅ Yes | ❌ No |
| **Full-text search** | ⚠️ Basic | ✅ Advanced (with PostgreSQL) |
| **Relationships** | ❌ No | ✅ Yes (FK, joins) |
| **Performance (100s posts)** | ✅ Fast | ✅ Fast |
| **Performance (1000s posts)** | ⚠️ Slower | ✅ Fast |
| **User management** | ❌ N/A | ✅ Required |

### Recommended Approach

**For most use cases**:
- **Blog posts**: Markdown files (default)
- **Users/auth**: Database (required for admin)
- **Optional**: Database posts if you need advanced queries

**Why markdown files?**
- Simple to edit (any text editor)
- Version control with Git
- No database migrations for content
- Portable (just copy files)

---

## Migrations

### Using Alembic

For production, use Alembic for schema migrations:

**1. Install Alembic**:
```bash
pip install alembic
```

**2. Initialize**:
```bash
alembic init alembic
```

**3. Configure** `alembic/env.py`:
```python
from fastapi_blog.admin.models import Base

target_metadata = Base.metadata

# For async:
from sqlalchemy.ext.asyncio import create_async_engine


def run_migrations_online():
  connectable = create_async_engine(config.get_main_option('sqlalchemy.url'))
  # ... rest of async migration logic
```

**4. Create migration**:
```bash
alembic revision --autogenerate -m "Add custom field"
```

**5. Apply**:
```bash
alembic upgrade head
```

**6. Disable auto-init**:
```python
fastapi_blog.add_admin_to_app(
    app,
    init_database=False,  # Let Alembic handle it
    ...
)
```

---

## Connection Pooling

### Default Settings

```python
create_async_engine(
  database_url,
  pool_size=5,  # Default
  max_overflow=10,  # Default
  pool_pre_ping=True,  # Check connection health
)
```

### Custom Pool Settings

```python
from fastapi_blog.admin.database import create_engine_and_session

# Not directly customizable in add_admin_to_app()
# Create your own engine:

from sqlalchemy.ext.asyncio import create_async_engine

engine = create_async_engine(
  'postgresql+asyncpg://...',
  pool_size=20,
  max_overflow=40,
  pool_timeout=30,
  pool_recycle=3600,
)

# Then manually configure admin with this engine
# (requires custom integration)
```

---

## Security

### Password Hashing

Passwords are hashed using **bcrypt** directly (the unmaintained `passlib`
wrapper was removed, see `fastapi_blog.admin.passwords`):

```python
from fastapi_blog.admin.passwords import get_password_hasher

hasher = get_password_hasher()

# Hash password
hashed = hasher.hash('my_password')

# Verify (old `passlib` `$2b$...` hashes stay valid)
is_valid = hasher.verify('my_password', hashed)
```

**Validation**:
- Min length: 8 characters
- Max length: 128 characters
- Bcrypt max bytes: 72 (enforced)

### SQL Injection Protection

FastAPI Blog uses SQLAlchemy ORM with parameterized queries, providing automatic protection against SQL injection.

### Session Security

- Sessions use signed cookies (via `itsdangerous`)
- Requires `secret_key` parameter
- HTTPS recommended for production

---

## Troubleshooting

### Database File Not Found (SQLite)

**Error**: `unable to open database file`

**Solution**: Ensure the directory exists:
```bash
mkdir -p ./data
```

Or specify an absolute path:
```python
database_url = 'sqlite+aiosqlite:////absolute/path/to/blog.db'
```

### Connection Pool Timeout

**Error**: `TimeoutError: QueuePool limit exceeded`

**Solution**: Increase pool size:
```python
# Create custom engine with larger pool
engine = create_async_engine(
  database_url,
  pool_size=20,
  max_overflow=40,
)
```

### Migration Conflicts

**Error**: Table already exists

**Solution**:
```python
# Disable auto-init
fastapi_blog.add_admin_to_app(
  app,
  auth_provider=lambda locale: create_auth_provider(locale),
  secret_key=os.environ['SECRET_KEY'],
  init_database=False,
)

# Use Alembic for migrations
alembic upgrade head
```

### PostgreSQL Connection Issues

**Error**: `could not connect to server`

**Check**:
1. PostgreSQL is running
2. Credentials are correct
3. `asyncpg` is installed: `pip install asyncpg`
4. Firewall allows connections

---

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `DATABASE_URL` | Database connection URL | `sqlite+aiosqlite:///./data/app.db` |
| `DEBUG` | Enable SQL query logging | `false` |

**Example**:
```bash
export DATABASE_URL="postgresql+asyncpg://user:pass@localhost/blog"
export DEBUG="true"
```

---

## API Reference

### Functions

#### `get_database_url()`
Returns the database URL from `DATABASE_URL` env var or default.

#### `create_engine_and_session(database_url=None)`
Creates async engine and session factory.

Returns: `(engine, AsyncSessionLocal)`

#### `init_db(engine)`
Async function to create all database tables.

#### `get_db(session_factory)`
Async generator for session dependency injection.

### Models

#### `User`
SQLAlchemy model for user authentication.

#### `Post`
SQLAlchemy model for database-backed blog posts (optional).

#### `Base`
DeclarativeBase for all models.

---

## Best Practices

### 1. Use Environment Variables for Production

```python
# Don't hardcode credentials
database_url = os.getenv('DATABASE_URL')
secret_key = os.getenv('SECRET_KEY')
```

### 2. Use PostgreSQL for Production

SQLite is great for development but use PostgreSQL for production:
- Better concurrency
- Network access
- Advanced features
- Proper backups

### 3. Backup Strategy

**For SQLite**:
```bash
# Backup
cp data/app.db data/app.db.backup

# Restore
cp data/app.db.backup data/app.db
```

**For PostgreSQL**:
```bash
# Backup
pg_dump -U user blog > backup.sql

# Restore
psql -U user blog < backup.sql
```

### 4. Use Alembic for Schema Changes

Don't rely on `init_database=True` for production. Use migrations:
```bash
alembic revision --autogenerate -m "Add field"
alembic upgrade head
```

### 5. Monitor Connection Pool

Enable logging in development:
```python
import logging

logging.basicConfig()
logging.getLogger('sqlalchemy.engine').setLevel(logging.INFO)
```

---

## Examples

### Minimal Setup (SQLite)

```python
import os
from fastapi import FastAPI
import fastapi_blog
from myapp.auth import create_auth_provider

app = FastAPI()

fastapi_blog.add_admin_to_app(
  app,
  auth_provider=lambda locale: create_auth_provider(locale),
  secret_key=os.environ['SECRET_KEY'],
)
```

### Production Setup (PostgreSQL)

```python
import os
from fastapi import FastAPI
import fastapi_blog
from myapp.auth import create_auth_provider

app = FastAPI()

fastapi_blog.add_admin_to_app(
  app,
  database_url=os.getenv('DATABASE_URL'),
  auth_provider=lambda locale: create_auth_provider(locale),
  secret_key=os.getenv('SECRET_KEY'),
  init_database=False,  # Use Alembic
)
```

### Custom Queries

```python
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from fastapi_blog.admin.database import get_db
from fastapi_blog.admin.models import User


@app.get('/api/users')
async def list_users(db: AsyncSession = Depends(get_db)):
  result = await db.execute(select(User).where(User.is_active == True))
  users = result.scalars().all()
  return [{'id': u.id, 'email': u.email} for u in users]
```

---

## Related Documentation

- [QUICKSTART.md](QUICKSTART.md) - Quick start guide
- [README.md](../README.md) - Project overview
- [SQLAlchemy Async](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html) - Official docs
- [Alembic](https://alembic.sqlalchemy.org/) - Migration tool

---

**Last Updated**: 2026-10-31
**Version**: 0.9.0 (in development)

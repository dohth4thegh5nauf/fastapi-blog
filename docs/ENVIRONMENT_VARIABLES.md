# Environment Variables Configuration

FastAPI Blog supports configuration through environment variables for common settings.

## Available Environment Variables

### Blog Configuration

#### `FASTAPI_BLOG_INCLUDE_API`

Controls whether to include REST API endpoints for post management.

**Default:** `false`

**Values:** `true`, `1`, `yes` (case-insensitive) → enables API, any other value → disables

**Example:**
```bash
export FASTAPI_BLOG_INCLUDE_API=true
```

**Usage:**
```python
from fastapi import FastAPI
import fastapi_blog

app = FastAPI()

# If FASTAPI_BLOG_INCLUDE_API=true, REST API will be included
fastapi_blog.add_blog_to_fastapi(app, prefix='blog')
# This is equivalent to: add_blog_to_fastapi(app, prefix='blog', include_api=True)
```

**Priority:** Explicit parameter > environment variable > default value

```python
# Explicit parameter takes priority
fastapi_blog.add_blog_to_fastapi(app, include_api=True)  # Always includes API

# Environment variable used if parameter not specified
fastapi_blog.add_blog_to_fastapi(app)  # Uses FASTAPI_BLOG_INCLUDE_API env var
```

### Admin Configuration

#### `FASTAPI_BLOG_ADMIN_LOGIN`

Default admin username for login.

**Default:** `admin`

**Example:**
```bash
export FASTAPI_BLOG_ADMIN_LOGIN=superuser
```

**Usage:**
```python
import fastapi_blog

# Uses username from environment variable
admins = fastapi_blog.add_admin_to_app(app)
# This is equivalent to: add_admin_to_app(app, admin_username='superuser')
```

#### `FASTAPI_BLOG_ADMIN_PASSWORD`

Default admin password for login.

**Default:** `Admin123!`

**Security Warning:** ⚠️ Change this in production! Never commit passwords to version control.

**Example:**
```bash
export FASTAPI_BLOG_ADMIN_PASSWORD=MySecurePassword123!
```

**Usage:**
```python
import fastapi_blog

# Uses password from environment variable
admins = fastapi_blog.add_admin_to_app(app)
# This is equivalent to: add_admin_to_app(app, admin_password='MySecurePassword123!')
```

**Priority:** Explicit parameter > environment variable > default value

```python
# Explicit parameters take priority
fastapi_blog.add_admin_to_app(
  app,
  admin_username='custom',
  admin_password='CustomPass123!',
)

# Environment variables used if parameters not specified
fastapi_blog.add_admin_to_app(app)  # Uses env vars if set
```

### Database Configuration

#### `DATABASE_URL`

Database connection URL for admin panel.

**Default:** `sqlite+aiosqlite:///./data/app.db`

**Examples:**
```bash
# SQLite
export DATABASE_URL="sqlite+aiosqlite:///./blog.db"

# PostgreSQL
export DATABASE_URL="postgresql+asyncpg://user:pass@localhost/blog"
```

**Usage:**
```python
import fastapi_blog

# Uses database URL from environment variable
admins = fastapi_blog.add_admin_to_app(app)
# This is equivalent to: add_admin_to_app(app, database_url='...')
```

See [DATABASE.md](DATABASE.md) for more details on database configuration.

#### `SECRET_KEY`

Secret key for session encryption.

**Default:** `change-me-in-production-please-use-strong-secret`

**Security Warning:** ⚠️ Always set this in production! Use a strong random value.

**Example:**
```bash
# Generate a secure random key
export SECRET_KEY=$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')
```

**Usage:**
```python
import fastapi_blog

# Uses secret key from environment variable
admins = fastapi_blog.add_admin_to_app(app)
# This is equivalent to: add_admin_to_app(app, secret_key='...')
```

## Complete Example

### Development (.env file)

```bash
# Blog configuration
FASTAPI_BLOG_INCLUDE_API=true

# Admin credentials (development only)
FASTAPI_BLOG_ADMIN_LOGIN=admin
FASTAPI_BLOG_ADMIN_PASSWORD=Admin123!

# Database
DATABASE_URL=sqlite+aiosqlite:///./dev.db

# Session encryption
SECRET_KEY=dev-secret-key-change-in-production
```

### Production (.env.production)

```bash
# Blog configuration
FASTAPI_BLOG_INCLUDE_API=false  # Disable public API in production

# Admin credentials (use strong passwords!)
FASTAPI_BLOG_ADMIN_LOGIN=admin
FASTAPI_BLOG_ADMIN_PASSWORD=VerySecurePassword123!WithSpecialChars

# Database (PostgreSQL for production)
DATABASE_URL=postgresql+asyncpg://bloguser:securepass@db.example.com:5432/blog

# Session encryption (use strong random key!)
SECRET_KEY=Xj8k2LmNp9qRs4TuVwXyZa1bCd3eF5gH7iJ0kL2mN4oP6qR8sT0uV2wX4yZ6aB8c
```

### Using in Application

```python
import os
from pathlib import Path
from dotenv import load_dotenv  # pip install python-dotenv
from fastapi import FastAPI
import fastapi_blog

# Load environment variables from .env file
load_dotenv()

# Or load from specific file
# load_dotenv('.env.production')

app = FastAPI()

# All configuration from environment variables
fastapi_blog.add_blog_to_fastapi(app, prefix='blog')
admins = fastapi_blog.add_admin_to_app(app)
```

## Docker Example

### Dockerfile

```dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# Environment variables can be set here or in docker-compose.yml
ENV FASTAPI_BLOG_INCLUDE_API=false
ENV DATABASE_URL=postgresql+asyncpg://user:pass@db:5432/blog

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### docker-compose.yml

```yaml
version: '3.8'

services:
  blog:
    build: .
    ports:
      - "8000:8000"
    environment:
      - FASTAPI_BLOG_INCLUDE_API=false
      - FASTAPI_BLOG_ADMIN_LOGIN=admin
      - FASTAPI_BLOG_ADMIN_PASSWORD=${ADMIN_PASSWORD}  # From .env
      - DATABASE_URL=postgresql+asyncpg://bloguser:blogpass@db:5432/blog
      - SECRET_KEY=${SECRET_KEY}  # From .env
    depends_on:
      - db
  
  db:
    image: postgres:16-alpine
    environment:
      - POSTGRES_USER=bloguser
      - POSTGRES_PASSWORD=blogpass
      - POSTGRES_DB=blog
    volumes:
      - postgres_data:/var/lib/postgresql/data

volumes:
  postgres_data:
```

### .env (for docker-compose)

```bash
ADMIN_PASSWORD=SecurePassword123!
SECRET_KEY=RandomSecretKey123456789
```

## Security Best Practices

### 1. Never Commit Secrets

Add to `.gitignore`:
```
.env
.env.production
.env.local
*.key
```

### 2. Use Strong Passwords

```bash
# Generate strong password
python3 -c 'import secrets; print(secrets.token_urlsafe(24))'
```

### 3. Use Strong Secret Keys

```bash
# Generate strong secret key
python3 -c 'import secrets; print(secrets.token_urlsafe(32))'
```

### 4. Different Credentials per Environment

Use separate credentials for:
- Development
- Staging
- Production

### 5. Rotate Secrets Regularly

Change passwords and secret keys periodically, especially after:
- Security incidents
- Team member changes
- Suspected compromises

## Troubleshooting

### Environment Variable Not Working

**Problem:** Environment variable set but not being used.

**Check:**
```python
import os
print(os.getenv('FASTAPI_BLOG_INCLUDE_API'))  # Should print your value
```

**Solutions:**
1. Ensure variable is exported: `export VAR=value`
2. Restart application after setting variable
3. Check for typos in variable name
4. Verify `.env` file is in correct location and loaded

### Priority Issues

**Problem:** Explicit parameter ignored.

**Check:** Explicit parameters always take priority over environment variables.

```python
# This always uses include_api=False, even if env var is 'true'
fastapi_blog.add_blog_to_fastapi(app, include_api=False)
```

**Solution:** Remove explicit parameter to use environment variable.

### Boolean Values Not Working

**Problem:** `FASTAPI_BLOG_INCLUDE_API=false` still enables API.

**Explanation:** Only `true`, `1`, `yes` (case-insensitive) enable the API. All other values (including `false`, `0`, `no`, empty string) disable it.

**Correct usage:**
```bash
# Enable
export FASTAPI_BLOG_INCLUDE_API=true

# Disable (any of these)
export FASTAPI_BLOG_INCLUDE_API=false
export FASTAPI_BLOG_INCLUDE_API=0
export FASTAPI_BLOG_INCLUDE_API=no
unset FASTAPI_BLOG_INCLUDE_API  # Uses default (false)
```

## Related Documentation

- [QUICKSTART.md](../QUICKSTART.md) - Quick start guide
- [DATABASE.md](DATABASE.md) - Database configuration
- [README.md](../README.md) - Project overview

---

**Last Updated:** 2026-05-15  
**Version:** 0.8.1+

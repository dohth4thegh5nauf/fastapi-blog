#!/bin/bash
# Quick demo script for fastapi-blog examples

set -e

REPO_ROOT="$(cd "$(dirname "$0")" && pwd)"

# Every example below uses the admin panel, which needs the `admin` extra
# (starlette-admin, sqlalchemy, passlib, ...). `uv sync` alone only
# installs the base dependencies, so pull in every extra here.
if command -v uv >/dev/null 2>&1; then
  ( cd "$REPO_ROOT" && uv sync --all-extras --quiet )
fi

cd "$REPO_ROOT/tests/examples"

# Activate virtual environment if it exists
if [ -f "$REPO_ROOT/.venv/bin/activate" ]; then
  source "$REPO_ROOT/.venv/bin/activate"
fi

# Ensure data directory exists
mkdir -p data

# Parse arguments
EXAMPLE="${1:-quickstart}"

case "$EXAMPLE" in
  quickstart)
    echo ""
    echo "🚀 Starting FastAPI Blog - Quickstart Example"
    echo ""
    echo "📍 Admin Panel: http://localhost:8000/admin"
    echo "📍 Blog:        http://localhost:8000/blog"
    echo "📍 API Docs:    http://localhost:8000/docs"
    echo ""
    echo "🔑 Demo login: admin / Admin123! (demo only)"
    echo ""
    uvicorn quickstart:app --reload
    ;;
  
  roles)
    echo ""
    echo "🚀 Starting FastAPI Blog - Admin with RBAC"
    echo ""
    echo "📍 Admin Panel: http://localhost:8000/admin"
    echo ""
    echo "🔑 Users:"
    echo "   - admin  / password  (full access)"
    echo "   - editor / password  (can edit, cannot delete)"
    echo "   - viewer / password  (read-only)"
    echo ""
    uvicorn admin_with_roles:app --reload
    ;;
  
  i18n)
    echo ""
    echo "🚀 Starting FastAPI Blog - Admin with Internationalization"
    echo ""
    echo "📍 Admin Panel: http://localhost:8000/admin"
    echo "🌍 Languages: English, Русский"
    echo ""
    echo "🔑 Demo login: admin / Admin123! (demo only)"
    echo ""
    uvicorn admin_i18n:app --reload
    ;;
  
  full)
    echo ""
    echo "🚀 Starting FastAPI Blog - Full Featured Example"
    echo ""
    echo "📍 Admin Panel: http://localhost:8000/admin"
    echo "✨ Features: i18n, custom fields, roles"
    echo ""
    echo "🔑 Demo login: admin / Admin123! (demo only)"
    echo ""
    uvicorn admin_full_featured:app --reload
    ;;
  
  editor)
    echo ""
    echo "🚀 Starting FastAPI Blog - Editor API (Legacy)"
    echo ""
    echo "📍 API Docs: http://localhost:8000/docs"
    echo "⚠️  This is the legacy editor - use quickstart for modern admin panel"
    echo ""
    uvicorn editor:app --reload
    ;;
  
  *)
    echo "Usage: ./demo.sh [example]"
    echo ""
    echo "Available examples:"
    echo "  quickstart  - Minimal setup with admin panel (default)"
    echo "  roles       - Admin with role-based access control"
    echo "  i18n        - Admin with internationalization (EN/RU)"
    echo "  full        - Full featured example with all bells and whistles"
    echo "  editor      - Legacy editor API (deprecated)"
    echo ""
    exit 1
    ;;
esac

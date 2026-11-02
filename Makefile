UV ?= uv
UV_RUN = $(UV) run --locked --extra dev --extra admin --extra jsonld

.PHONY: all install tag lint format mypy test test-pdb run run_defaults run_modified_all run_prefix_change run_prefix_none run_favorite_post_ids setup_examples run_editor run_quickstart run_admin_roles run_admin_i18n run_admin_full

VERSION=v$(shell grep -m 1 version pyproject.toml | tr -s ' ' | tr -d '"' | tr -d "'" | cut -d' ' -f3)

tag:
	echo "Tagging version $(VERSION)"
	git tag -a $(VERSION) -m "Creating version $(VERSION)"
	git push origin $(VERSION)

install:
	$(UV) sync --locked --extra dev --extra admin --extra jsonld

all: lint mypy test

lint:
	$(UV_RUN) ruff check .
	$(UV_RUN) ruff format . --check

format:
	$(UV_RUN) ruff check . --fix
	$(UV_RUN) ruff format .

mypy:
	$(UV_RUN) mypy .

test:
	$(UV_RUN) coverage run -m pytest
	$(UV_RUN) coverage report -m
	$(UV_RUN) coverage html

test-pdb:
	$(UV_RUN) pytest --pdb

run:
	$(MAKE) run_defaults

run_defaults:
	cd tests/examples && $(UV_RUN) uvicorn defaults:app --reload

run_modified_all:
	cd tests/examples && $(UV_RUN) uvicorn modified_all:app --reload

run_prefix_change:
	cd tests/examples && $(UV_RUN) uvicorn prefix_change:app --reload

run_prefix_none:
	cd tests/examples && $(UV_RUN) uvicorn prefix_none:app --reload

run_favorite_post_ids:
	cd tests/examples && $(UV_RUN) uvicorn favorite_post_ids:app --reload

# Create data directory for examples
setup_examples:
	mkdir -p tests/examples/data

run_editor:
	cd tests/examples && mkdir -p data && $(UV_RUN) uvicorn editor:app --reload

run_quickstart:
	@echo "\n🚀 Starting FastAPI Blog - Quickstart Example\n"
	@echo "📍 Admin Panel: http://localhost:8000/admin"
	@echo "🔑 DEV ONLY login (insecure_dev=True): admin / Admin123!\n"
	cd tests/examples && mkdir -p data && $(UV_RUN) uvicorn quickstart:app --reload

run_admin_roles:
	@echo "\n🚀 Starting FastAPI Blog - Admin with RBAC\n"
	@echo "📍 Admin Panel: http://localhost:8000/admin"
	@echo "🔑 DEV ONLY users (insecure_dev=True): admin, editor, viewer\n"
	cd tests/examples && mkdir -p data && $(UV_RUN) uvicorn admin_with_roles:app --reload

run_admin_i18n:
	@echo "\n🚀 Starting FastAPI Blog - Admin with i18n (EN/RU)\n"
	@echo "📍 Admin Panel: http://localhost:8000/admin"
	@echo "🌍 Languages: English, Русский\n"
	cd tests/examples && $(UV_RUN) uvicorn admin_i18n:app --reload

run_admin_full:
	@echo "\n🚀 Starting FastAPI Blog - Full Featured Example\n"
	@echo "📍 Admin Panel: http://localhost:8000/admin"
	@echo "✨ Features: i18n, custom fields, roles\n"
	cd tests/examples && $(UV_RUN) uvicorn admin_full_featured:app --reload

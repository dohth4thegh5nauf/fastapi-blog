

VERSION=v$(shell grep -m 1 version pyproject.toml | tr -s ' ' | tr -d '"' | tr -d "'" | cut -d' ' -f3)

tag:
	echo "Tagging version $(VERSION)"
	git tag -a $(VERSION) -m "Creating version $(VERSION)"
	git push origin $(VERSION)

install:
	pip install uv
	if [ -n "$$VIRTUAL_ENV" ] || [ -f "pyvenv.cfg" ]; then \
		uv pip install -e '.[dev,admin,jsonld]'; \
	else \
		uv pip install --system -e '.[dev,admin,jsonld]'; \
	fi

all:
	make lint
	make mypy
	make test

lint:
	ruff check .
	ruff format . --check

format:
	ruff check . --fix
	ruff format .

mypy:
	mypy .

test:
	coverage run -m pytest .
	coverage report -m
	coverage html

test-pdb:
	pytest --pdb .

run:
	make run_defaults

run_defaults:
	cd tests/examples && uvicorn defaults:app --reload	

run_modified_all:
	cd tests/examples && uvicorn modified_all:app --reload	

run_prefix_change:
	cd tests/examples && uvicorn prefix_change:app --reload		

run_prefix_none:
	cd tests/examples && uvicorn prefix_none:app --reload

run_favorite_post_ids:
	cd tests/examples && uvicorn favorite_post_ids:app --reload

# Create data directory for examples
setup_examples:
	mkdir -p tests/examples/data

run_editor:
	cd tests/examples && mkdir -p data && uvicorn editor:app --reload

run_quickstart:
	@echo "\n🚀 Starting FastAPI Blog - Quickstart Example\n"
	@echo "📍 Admin Panel: http://localhost:8000/admin"
	@echo "🔑 Login: admin / Admin123!\n"
	cd tests/examples && mkdir -p data && uvicorn quickstart:app --reload

run_admin_roles:
	@echo "\n🚀 Starting FastAPI Blog - Admin with RBAC\n"
	@echo "📍 Admin Panel: http://localhost:8000/admin"
	@echo "🔑 Users: admin/Admin123!, editor/Editor123!, viewer/Viewer123!\n"
	cd tests/examples && mkdir -p data && uvicorn admin_with_roles:app --reload

run_admin_i18n:
	@echo "\n🚀 Starting FastAPI Blog - Admin with i18n (EN/RU)\n"
	@echo "📍 Admin Panel: http://localhost:8000/admin"
	@echo "🌍 Languages: English, Русский\n"
	cd tests/examples && mkdir -p data && uvicorn admin_i18n:app --reload

run_admin_full:
	@echo "\n🚀 Starting FastAPI Blog - Full Featured Example\n"
	@echo "📍 Admin Panel: http://localhost:8000/admin"
	@echo "✨ Features: i18n, custom fields, roles\n"
	cd tests/examples && mkdir -p data && uvicorn admin_full_featured:app --reload
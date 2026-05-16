# Изучение кодовой базы FastAPI Blog

## Общая информация о проекте

**FastAPI Blog** - это библиотека для создания блогов на базе FastAPI с поддержкой:
- Markdown-постов с YAML frontmatter
- Административной панели (starlette-admin)
- Интернационализации (i18n)
- Role-Based Access Control (RBAC)
- REST API для программного управления постами

**Версия**: 0.8.0
**Python**: 3.12+
**Лицензия**: MIT

## Архитектура проекта

### Три типа endpoints:

1. **`/blog`** - публичный блог (REST API, доступен в `/docs`)
   - GET `/blog/` - главная страница
   - GET `/blog/posts` - список постов
   - GET `/blog/posts/{slug}` - отдельный пост
   - GET `/blog/tags` - список тегов
   - GET `/blog/tags/{tag}` - посты по тегу

2. **`/admin`** - административная панель (Web UI, НЕ в `/docs`)
   - Веб-интерфейс для управления контентом
   - Управление пользователями
   - Управление постами через WYSIWYG редактор
   - Поддержка нескольких языков интерфейса

3. **`/api/posts`** - REST API для управления постами (опционально, в `/docs` если `include_api=True`)
   - POST `/api/posts/create/{slug}` - создать пост
   - PUT `/api/posts/update/{slug}` - обновить пост
   - DELETE `/api/posts/delete/{slug}` - удалить пост

### Структура директорий:

```
fastapi-blog/
├── src/fastapi_blog/
│   ├── __init__.py              # Основные функции setup_fastapi_blog()
│   ├── main.py                  # add_blog_to_fastapi()
│   ├── router.py                # Роутеры для блога
│   ├── helpers.py               # Вспомогательные функции
│   ├── models.py                # Pydantic модели для постов
│   ├── admin/                   # Административная панель
│   │   ├── __init__.py          # add_admin_to_app()
│   │   ├── auth_provider.py     # Аутентификация
│   │   ├── database.py          # SQLAlchemy + async
│   │   ├── models.py            # User, Post (SQLAlchemy)
│   │   ├── models_role.py       # Role, UserWithRoles
│   │   ├── views.py             # ModelViews для админки
│   │   ├── views_role.py        # RoleModelView, UserWithRolesModelView
│   │   ├── i18n.py              # Поддержка локализации
│   │   ├── fields.py            # MarkdownField, TagsField, SlugField
│   │   ├── markdown_crud.py     # CRUD для markdown файлов
│   │   ├── templates/           # Кастомные шаблоны starlette-admin
│   │   └── translations/        # en.yaml, ru.yaml
│   └── templates/               # Шаблоны для блога
│       ├── index.html
│       ├── post.html
│       ├── posts.html
│       ├── tags.html
│       └── ...
├── tests/
│   ├── test_*.py                # Unit тесты
│   ├── test_sidebar_links.py   # Тесты локализации ссылок
│   └── examples/                # Примеры использования
│       ├── quickstart.py
│       ├── admin_i18n.py
│       ├── admin_with_roles.py
│       └── ...
├── docs/                        # Документация
│   ├── DATABASE.md
│   ├── ROLE_MANAGEMENT.md
│   └── ...
├── pyproject.toml               # Конфигурация проекта
├── Makefile                     # Команды для разработки
└── README.md
```

## Ключевые компоненты

### 1. Хранение данных

**Hybrid storage approach:**
- **Markdown файлы** - основное хранилище постов блога
  - Директория: `posts/` (по умолчанию)
  - Формат: YAML frontmatter + Markdown content
  - Плюсы: Git-friendly, версионирование, простота редактирования
  
- **SQLite/PostgreSQL база данных** - для админ-панели
  - URL по умолчанию: `sqlite+aiosqlite:///./data/app.db`
  - Модели: User, Post (опционально), Role, UserWithRoles
  - Async SQLAlchemy 2.0

### 2. Интернационализация (i18n)

**Две системы i18n:**

1. **Blog i18n** - язык контента блога
   - Параметр: `locales=["en", "ru"]`
   - Default locale: чистые URL без префикса (`/blog/`)
   - Other locales: URL с префиксом (`/ru/blog/`)
   - Переключение через middleware на основе Accept-Language

2. **Admin i18n** - язык интерфейса админки
   - Отдельные Admin instances для каждой локали
   - Default: `/admin` (английский)
   - Other: `/ru/admin` (русский)
   - Переводы в `admin/translations/*.yaml`

### 3. Аутентификация

**Admin panel:**
- Session-based authentication
- SessionMiddleware + signed cookies
- SimpleAuthProvider (hardcoded credentials для dev)
- В production: интеграция с JWT или БД пользователей

**REST API (опционально):**
- Требует тех же credentials что и admin
- Используется для программного доступа

### 4. RBAC (Role-Based Access Control)

**Опциональная функция:**
- Параметр: `enable_role_management=True`
- Модели: Role, UserWithRoles
- RoleModelView, UserWithRolesModelView
- Доступ только для root admin пользователя

## Текущее состояние проекта

### Недавние изменения (последние коммиты):

1. **271667c** - "Fix: Correct URL generation in admin navigation for i18n"
   - Добавлен уникальный `route_name` для каждого admin instance
   - Удалены кастомные `layout.html` и `macros/views.html`
   - Цель: исправить генерацию URL в навигации админки

2. **8358fc8** - "deluge"
   - Добавлены кастомные `layout.html` и `macros/views.html`
   - Добавлен тест `test_sidebar_links.py`
   - Попытка исправить проблему с locale-aware ссылками

3. **bf53be1** - "add regression tests for sidebar link locale handling"
   - Тесты для проверки локализации ссылок в блоге

### Известные проблемы (из TODO.md):

**Основная проблема:** Ссылки в sidebar админ-панели не учитывают текущую локаль.

**Описание:**
- При переходе на `/ru/admin/user/list`, все ссылки в sidebar ведут на `/admin/...` вместо `/ru/admin/...`
- Проблема в том, что starlette-admin генерирует ссылки через `view.url(request)`, который использует `request.url_for(route_name)`
- `url_for` не знает о locale-префиксе в base_url

**Предложенное решение (из TODO.md):**
1. Добавить Jinja2 фильтр `rebase_url` в `_create_admin_for_locale()`
2. Переопределить `macros/views.html` чтобы применять этот фильтр
3. Заменить все `view.url(request)` на `view.url(request) | rebase_url`

**Но есть более фундаментальная проблема:**
- Тест `test_admin_sidebar_links_respect_locale` падает
- Login не работает правильно при нескольких Admin instances
- Каждый admin создает свой `/login` endpoint, они конфликтуют

## Тесты

### Статус тестов:

**Успешно проходят:**
- `test_sidebar_links_use_ru_locale` ✅
- `test_sidebar_links_use_default_locale` ✅
- `test_tag_links_in_tags_page_respect_locale` ✅
- `test_post_links_in_listing_respect_locale` ✅
- `test_tag_links_on_post_page_respect_locale` ✅
- `test_sidebar_links_on_default_locale_homepage` ✅
- `test_sidebar_links_on_non_default_locale_homepage` ✅
- `test_no_unprefixed_blog_links_on_ru_pages` ✅
- `test_no_redirect_from_ru_blog_to_default` ✅

**Падают:**
- `test_admin_sidebar_links_respect_locale` ❌

**Причина:** Не удается залогиниться в admin из-за конфликта login endpoints между разными locale instances.

## Зависимости

### Core dependencies:
- `fastapi>=0.116.2`
- `starlette-admin[i18n]>=0.16.0`
- `sqlalchemy[asyncio]>=2.0.0`
- `aiosqlite>=0.19.0`
- `jinja2>=3.1.6`
- `markdown>=3.9`
- `pyyaml>=6.0.2`

### Dev dependencies:
- `pytest>=8.4.2`
- `httpx>=0.28.1`
- `ruff>=0.13.0`
- `mypy>=1.18.1`
- `coverage>=7.10.6`

## API

### Основные функции:

**`setup_fastapi_blog(app, **kwargs)`**
- Unified setup - конфигурирует и блог, и админку одной функцией
- Рекомендуется для новых проектов

**`add_blog_to_fastapi(app, **kwargs)`**
- Добавляет только блог (без админки)
- Параметры: prefix, locales, include_api, и т.д.

**`add_admin_to_app(app, **kwargs)`**
- Добавляет только админ-панель
- Параметры: locales, admin_username, admin_password, enable_role_management

### Примеры использования:

См. `tests/examples/` для полных примеров:
- `quickstart.py` - минимальная настройка
- `admin_i18n.py` - многоязычная админка
- `admin_with_roles.py` - с RBAC
- `admin_full_featured.py` - все возможности

## Инструкция по разработке

### Установка:
```bash
make install     # Устанавливает зависимости через venv
```

### Запуск тестов:
```bash
make test        # Все тесты с coverage
make lint        # Проверка стиля кода
make mypy        # Проверка типов
make all         # lint + mypy + test
```

### Запуск примеров:
```bash
./demo.sh quickstart    # Минимальный пример
./demo.sh i18n          # С интернационализацией
./demo.sh roles         # С RBAC
./demo.sh full          # Все возможности
```

### Code style:
- Ruff для форматирования и линтинга
- Type hints обязательны для public API
- Docstrings для public функций
- 2 spaces для отступов (согласно AI.md)

## Рекомендации по доработке

### Приоритет 1: Исправить проблему с admin sidebar links

**Варианты решения:**

**Вариант A:** Использовать единственный Admin instance с middleware для переключения языка
- Плюсы: Нет конфликтов login endpoints
- Минусы: Требует переработки текущей архитектуры

**Вариант B:** Исправить текущую multi-instance архитектуру
- Добавить shared session store (Redis)
- Унифицировать login endpoint
- Реализовать `rebase_url` фильтр как предложено в TODO.md

**Вариант C:** Отказаться от URL-based locale switching в админке
- Использовать cookie/session для выбора языка
- Все admin instances на `/admin`
- Language switcher меняет locale в session

### Приоритет 2: Улучшить документацию

- Добавить диаграммы архитектуры
- Больше примеров в README
- API reference documentation
- Troubleshooting guide

### Приоритет 3: Расширить тесты

- E2E тесты для admin panel
- Тесты для RBAC
- Тесты для markdown CRUD API
- Performance тесты для большого количества постов

## Полезные ссылки

- **Репозиторий:** https://github.com/pydanny/fastapi-blog
- **Starlette Admin docs:** https://jowilf.github.io/starlette-admin/
- **FastAPI docs:** https://fastapi.tiangolo.com/

---

**Дата анализа:** 2026-05-16
**Версия проекта:** 0.8.0

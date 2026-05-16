# Анализ кодовой базы FastAPI Blog

**Дата анализа:** 2026-05-15  
**Версия:** 0.8.1+  
**Статус:** Production-ready

## 📋 Обзор проекта

**FastAPI Blog** — это современное решение для создания блогов на базе FastAPI с полнофункциональной административной панелью.

### Ключевые характеристики

- **Язык:** Python 3.12+
- **Фреймворк:** FastAPI
- **База данных:** SQLite (по умолчанию) / PostgreSQL / MySQL
- **Хранение контента:** Markdown файлы + опциональная БД
- **Аутентификация:** Session-based + HTTP Basic Auth
- **Админ-панель:** starlette-admin
- **Тестирование:** 117 тестов, покрытие ~39%
- **CI/CD:** GitHub Actions

---

## 🏗️ Архитектура

### Трёхуровневая структура endpoint'ов

| Путь | Тип | Назначение | В `/docs`? |
|------|-----|-----------|------------|
| `/blog` | REST API | Публичный блог (read-only) | ✅ Да |
| `/admin` | Web UI | Веб-интерфейс управления контентом | ❌ Нет |
| `/api/posts` | REST API | Программное управление постами | ✅ Да (если `include_api=True`) |

### Гибридное хранилище данных

Проект использует **два отдельных хранилища**:

1. **Markdown файлы** — основное хранилище постов блога
   - Версионный контроль через Git
   - Простое редактирование в любом текстовом редакторе
   - Портативность

2. **База данных** — управление пользователями и опциональное хранение постов
   - Пользователи и аутентификация
   - Роли и права доступа (RBAC)
   - Опциональное хранение постов (альтернатива markdown)

---

## 📁 Структура проекта

```
fastapi-blog/
├── src/fastapi_blog/              # Основной пакет
│   ├── __init__.py               # Публичный API
│   ├── main.py                   # Интеграция с FastAPI
│   ├── router.py                 # Роутеры блога
│   ├── helpers.py                # Утилиты
│   ├── models.py                 # Модели данных
│   ├── auth.py                   # Унифицированная аутентификация
│   ├── editor.py                 # Редактор постов (deprecated)
│   ├── admin/                    # Админ-панель
│   │   ├── __init__.py          # Настройка админки
│   │   ├── models.py            # Модели БД (User, Post)
│   │   ├── models_role.py       # Модели RBAC (Role, UserWithRoles)
│   │   ├── views.py             # Представления админки
│   │   ├── views_role.py        # Представления для ролей
│   │   ├── auth_provider.py     # Провайдер аутентификации
│   │   ├── database.py          # Настройка БД
│   │   ├── fields.py            # Кастомные поля (Markdown, Tags, Slug)
│   │   ├── i18n.py              # Интернационализация
│   │   ├── markdown_model.py    # Модель для markdown постов
│   │   ├── markdown_crud.py     # CRUD для markdown
│   │   ├── templates/           # Шаблоны админки
│   │   └── translations/        # Переводы (en, ru)
│   ├── templates/                # Публичные шаблоны блога
│   └── translations/             # Переводы блога
├── tests/                        # Тесты (117 тестов)
│   ├── examples/                 # Примеры конфигураций
│   │   ├── quickstart.py        # Базовый пример
│   │   ├── admin_with_roles.py  # RBAC пример
│   │   ├── admin_i18n.py        # i18n пример
│   │   └── admin_full_featured.py
│   ├── test_*.py                # Unit и integration тесты
│   └── ...
├── docs/                         # Документация
│   ├── DATABASE.md              # Архитектура БД
│   ├── ENVIRONMENT_VARIABLES.md # Конфигурация через env
│   ├── ROLE_MANAGEMENT.md       # RBAC документация
│   └── CODEBASE_ANALYSIS.md     # Этот документ
├── .github/workflows/            # CI/CD
│   ├── ci.yml                   # Основной CI pipeline
│   └── test.yml                 # Альтернативный CI
├── pyproject.toml               # Конфигурация проекта
├── Makefile                     # Команды разработки
├── README.md                    # Основная документация
├── QUICKSTART.md                # Быстрый старт
├── CONTRIBUTING.md              # Гайд для контрибьюторов
├── AI.md                        # Инструкции для AI
└── changelog.md                 # История изменений
```

---

## 🎯 Ключевые функции

### Функции блога

- ✅ **Markdown посты** с YAML frontmatter
- ✅ **Подсветка синтаксиса** для кодовых блоков
- ✅ **Адаптивный дизайн** (responsive)
- ✅ **Тёмная тема**
- ✅ **Переопределяемые шаблоны**
- ✅ **SEO-оптимизация** с генерацией sitemap
- ✅ **Теги и категории**
- ✅ **Избранные статьи** на главной странице

### Функции админ-панели

- ✅ **Современный UI** (powered by starlette-admin)
- ✅ **Управление пользователями** с RBAC
- ✅ **Визуальный редактор** постов с Markdown
- ✅ **Интернационализация** (английский/русский)
- ✅ **Безопасная аутентификация** с bcrypt
- ✅ **Кастомные поля** (Markdown, Tags, Slugs)
- ✅ **Поиск, фильтрация, пагинация**
- ✅ **Переключатель темы** (светлая/тёмная/авто)
- ✅ **Изоляция шаблонов** админки от публичных

### Безопасность

- 🔒 **Bcrypt хеширование** паролей
- 🔒 **Валидация паролей** (длина, сложность)
- 🔒 **Валидация secret_key** с предупреждениями
- 🔒 **Защита от SQL injection** (SQLAlchemy ORM)
- 🔒 **HTML санитизация** (nh3)
- 🔒 **CSRF защита**
- 🔒 **Пароли не логируются** (даже в DEBUG режиме)
- 🔒 **Session-based аутентификация** с подписанными cookies

---

## 🧪 Тестирование

### Статистика тестов

- **Всего тестов:** 117
- **Прошедших:** 116
- **Пропущенных:** 1
- **Покрытие кода:** ~39% (основной функционал покрыт)
- **Время выполнения:** ~8 секунд

### Категории тестов

| Категория | Файл | Тестов | Описание |
|-----------|------|--------|----------|
| Админ шаблоны | `test_admin_template_isolation.py` | 3 | Изоляция шаблонов |
| Админ темы | `test_admin_theme.py` | 7 | Переключатель тем |
| API auth | `test_api_unified_auth.py` | 3 | Унифицированная аутентификация |
| i18n | `test_blog_i18n.py` | 19 | Интернационализация блога |
| Редактор | `test_editor.py` | 29 | CRUD операции |
| Helpers | `test_helpers.py` | 4 | Вспомогательные функции |
| Lifespan | `test_lifespan.py` | 1 | Композиция lifespan |
| Markdown | `test_markdown_model.py` | 9 | Markdown модель |
| Пароли | `test_password_*.py` | 11 | Безопасность паролей |
| RBAC | `test_role_management_access.py` | 9 | Управление ролями |
| Router | `test_router.py` | 1 | Маршрутизация |
| Session | `test_session_middleware_duplication.py` | 4 | Middleware |
| Setup | `test_setup_fastapi_blog.py` | 5 | Унифицированная настройка |
| Auth | `test_unified_auth.py` | 6 | Унифицированная аутентификация |
| Secrets | `test_weak_secret_validation.py` | 6 | Валидация секретных ключей |

### Инструменты качества кода

```bash
# Линтинг и форматирование
make lint         # Проверка с ruff
make format       # Авто-форматирование

# Проверка типов
make mypy         # Статический анализ типов

# Тестирование
make test         # Тесты с покрытием
make test-pdb     # Тесты с отладчиком

# Всё вместе
make all          # lint + mypy + test
```

---

## 🚀 Основные API

### 1. Унифицированная настройка (рекомендуется)

```python
import fastapi_blog
from fastapi import FastAPI

app = FastAPI()

fastapi_blog.setup_fastapi_blog(
    app,
    posts_dirname="posts",
    include_api=False,
    locales=["en", "ru"],
    default_locale="en",
    admin_username="admin",
    admin_password="secure_password",
    secret_key="your-secret-key",
    enable_role_management=False,
)
```

### 2. Раздельная настройка (больше контроля)

```python
# Добавить блог
fastapi_blog.add_blog_to_fastapi(
    app,
    prefix="blog",
    locales=["en", "ru"],
    include_api=True,  # REST API для постов
)

# Добавить админ-панель
fastapi_blog.add_admin_to_app(
    app,
    admin_username="admin",
    admin_password="secure_password",
    secret_key="your-secret-key",
    enable_role_management=True,  # RBAC
)
```

### 3. Конфигурация через переменные окружения

```bash
# .env
FASTAPI_BLOG_INCLUDE_API=true
FASTAPI_BLOG_ADMIN_LOGIN=admin
FASTAPI_BLOG_ADMIN_PASSWORD=secure_password
DATABASE_URL=postgresql+asyncpg://user:pass@localhost/blog
SECRET_KEY=your-generated-secret-key
```

---

## 🌍 Интернационализация (i18n)

### Поддерживаемые языки

- 🇬🇧 **English** (en)
- 🇷🇺 **Русский** (ru)

### Структура переводов

```
src/fastapi_blog/
├── admin/translations/
│   ├── en.yaml          # Админ-панель (английский)
│   └── ru.yaml          # Админ-панель (русский)
└── translations/
    ├── en/LC_MESSAGES/  # Блог (английский)
    └── ru/LC_MESSAGES/  # Блог (русский)
```

### Использование

```python
# Админ-панель: автоматическая локализация по locale в URL
# /admin/en - английский
# /admin/ru - русский

# Блог: локализация по Accept-Language или URL
# /blog/en/posts - английский
# /blog/ru/posts - русский
```

### Переключатель языков

- Автоматически отображается при `locales=["en", "ru"]`
- Скрывается при одном языке
- Сохраняет текущую страницу при переключении
- JavaScript редирект на новый язык

---

## 🗄️ База данных

### Модели

#### User (базовая модель пользователя)

```python
class User:
    id: int
    email: str (unique)
    hashed_password: str
    is_active: bool
    is_admin: bool
    created_at: datetime
    updated_at: datetime | None
```

#### UserWithRoles (расширенная модель с RBAC)

```python
class UserWithRoles(User):
    roles: list[Role]
    
    def has_role(self, role_name: str) -> bool
    def has_any_role(*role_names: str) -> bool
```

#### Role (роли для RBAC)

```python
class Role:
    id: int
    name: str (unique)
    description: str | None
    is_active: bool
    users: list[UserWithRoles]
    created_at: datetime
    updated_at: datetime | None
```

#### Post (опциональная модель поста в БД)

```python
class Post:
    id: int
    slug: str (unique)
    title: str
    content: str
    description: str | None
    tags: list
    published: bool
    publish_date: datetime | None
    created_at: datetime
    updated_at: datetime | None
```

### Поддерживаемые БД

- ✅ **SQLite** (по умолчанию) — `sqlite+aiosqlite:///./data/app.db`
- ✅ **PostgreSQL** — `postgresql+asyncpg://user:pass@host/db`
- ✅ **MySQL/MariaDB** — `mysql+aiomysql://user:pass@host/db`

### Async SQLAlchemy 2.0

Проект использует современный async подход:

```python
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

engine = create_async_engine(database_url)
AsyncSessionLocal = async_sessionmaker(engine)

# Dependency injection
async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session
```

---

## 🔐 Аутентификация

### Унифицированная система аутентификации

Проект использует **единую систему аутентификации** для админки и API:

```python
from fastapi_blog.auth import require_current_user

@app.get("/protected")
async def protected(user: User = Depends(require_current_user)):
    return {"message": f"Hello, {user.email}"}
```

### Поддерживаемые методы

1. **Session-based** (админ-панель)
   - Cookies с signed session
   - Форма логина
   - Защита CSRF

2. **HTTP Basic Auth** (REST API)
   - Заголовок `Authorization: Basic <base64>`
   - Те же учётные данные

### Управление ролями (RBAC)

```python
# Включить RBAC
fastapi_blog.add_admin_to_app(
    app,
    enable_role_management=True,
)

# Проверка ролей
if user.has_role('admin'):
    # Полный доступ
    pass

if user.has_any_role('admin', 'editor'):
    # Доступ для админов и редакторов
    pass
```

#### Роли по умолчанию

- **admin** — полный доступ ко всем функциям
- **editor** — создание и редактирование контента
- **viewer** — только просмотр (read-only)

---

## 📝 Markdown посты

### Структура поста

```markdown
---
title: "Заголовок поста"
date: "2024-01-15T12:00:00Z"
published: true
tags:
  - fastapi
  - python
description: "Краткое описание"
author: "Автор"
image: "/static/image.jpg"
---

# Содержимое

Текст поста с **markdown** разметкой.

\`\`\`python
print("Hello, World!")
\`\`\`
```

### Frontmatter поля

| Поле | Тип | Обязательное | Описание |
|------|-----|--------------|----------|
| `title` | str | ✅ | Заголовок поста |
| `date` | ISO8601 | ✅ | Дата публикации |
| `published` | bool | ✅ | Опубликован ли пост |
| `tags` | list[str] | ❌ | Теги поста |
| `description` | str | ❌ | Краткое описание |
| `author` | str | ❌ | Автор |
| `image` | str | ❌ | Изображение |

### Функции работы с markdown

```python
from fastapi_blog import helpers

# Загрузить посты
posts = helpers.list_posts(posts_dirname="posts", strict=True)

# Конвертировать markdown в HTML
html = helpers.markdown(content, sanitize=True)

# Загрузить контент из файла
content = helpers.load_content_from_markdown_file("posts/example.md")
```

---

## 🛠️ CI/CD

### GitHub Actions Workflows

#### 1. CI Pipeline (`.github/workflows/ci.yml`)

```yaml
jobs:
  test:
    strategy:
      matrix:
        python-version: ["3.12", "3.13"]
    steps:
      - Install dependencies with uv
      - Lint with ruff
      - Type check with mypy
      - Test with pytest + coverage
      - Upload coverage to Codecov
  
  security:
    steps:
      - Safety check (dependencies)
      - Bandit security scan
```

**Статус:** ✅ Все проверки проходят

#### 2. Test Workflow (`.github/workflows/test.yml`)

Альтернативный упрощённый CI:
- Линтинг с ruff
- Тесты с pytest

### Команды для локальной проверки

```bash
# Запустить полный CI локально
make all

# Отдельные проверки
make lint    # Ruff
make mypy    # Type checking
make test    # Tests + coverage
```

---

## 📦 Зависимости

### Основные (production)

```toml
fastapi >= 0.116.2
jinja2 >= 3.1.6
markdown >= 3.9
nh3 >= 0.2.18          # HTML sanitization
pydantic >= 2.9
pyyaml >= 6.0.2
uvicorn >= 0.35.0
starlette-admin >= 0.16.0
sqlalchemy >= 2.0.0
aiosqlite >= 0.19.0
passlib[bcrypt] >= 1.7.4
redis >= 5.0.0
```

### Разработка (dev)

```toml
httpx >= 0.28.1
ruff >= 0.13.0
pytest >= 8.4.2
coverage >= 7.10.6
mypy >= 1.18.1
```

---

## 📚 Документация

### Доступная документация

| Файл | Описание |
|------|----------|
| `README.md` | Основная документация |
| `QUICKSTART.md` | Быстрый старт с примерами |
| `CONTRIBUTING.md` | Гайд для контрибьюторов |
| `docs/DATABASE.md` | Архитектура базы данных |
| `docs/ENVIRONMENT_VARIABLES.md` | Конфигурация через env |
| `docs/ROLE_MANAGEMENT.md` | RBAC документация |
| `LANGUAGE_SWITCHER.md` | Переключатель языков |
| `changelog.md` | История изменений |
| `AI.md` | Инструкции для AI ассистентов |

### Примеры использования

Все примеры в `tests/examples/`:

```bash
# Базовый пример
./demo.sh quickstart

# RBAC
./demo.sh roles

# Интернационализация
./demo.sh i18n

# Полнофункциональный
./demo.sh full
```

---

## 🔄 История изменений (последние версии)

### v0.8.1 (2026-05-15)

**Добавлено:**
- Унифицированный фасад `setup_fastapi_blog()`
- Валидация слабых `secret_key` с предупреждениями
- `.env.example` с документацией
- 21 новый тест

**Исправлено:**
- 🔴 **КРИТИЧНО:** Пароли больше не логируются
- Композиция lifespan корректно обёрнута
- Изоляция шаблонов админки

**Безопасность:**
- Пароли никогда не логируются (даже в DEBUG)
- Детектор слабых секретных ключей

### v0.8.0 (2026-05-12)

**Добавлено:**
- Админ-панель на базе starlette-admin
- RBAC с `enable_role_management`
- i18n для английского и русского
- Раздельные админки по локалям (`/admin/en`, `/admin/ru`)
- Markdown CRUD для управления постами
- Кастомные поля
- Переключатель темы
- Изоляция шаблонов

---

## 🚀 Развёртывание

### Development

```bash
# Установка
git clone https://github.com/pydanny/fastapi-blog.git
cd fastapi-blog
make install

# Запуск
./demo.sh quickstart
```

### Production (Docker)

```bash
# Использовать готовый образ
docker run -d -p 8000:8000 \
  -e DATABASE_URL="postgresql+asyncpg://..." \
  -e SECRET_KEY="$(python -c 'import secrets; print(secrets.token_hex(32))')" \
  ghcr.io/pydanny/fastapi-blog:latest
```

### Production (традиционное развёртывание)

```bash
# Установка
pip install fastapi-blog

# Создать приложение
# main.py

# Запустить с gunicorn + uvicorn workers
gunicorn main:app -w 4 -k uvicorn.workers.UvicornWorker
```

---

## 🤝 Разработка

### Стиль кода

- **Форматирование:** ruff
- **Линтинг:** ruff
- **Типы:** mypy (strict mode отключён для гибкости)
- **Тесты:** pytest
- **Покрытие:** coverage

### Правила коммитов

```
<type>: <subject>

<body>
```

**Типы:**
- `feat:` — новая функция
- `fix:` — исправление бага
- `docs:` — изменения в документации
- `test:` — добавление тестов
- `refactor:` — рефакторинг кода
- `chore:` — рутинные задачи

### Workflow контрибьютора

```bash
# 1. Fork репозитория
# 2. Клонировать и настроить
git clone https://github.com/YOUR_USERNAME/fastapi-blog.git
cd fastapi-blog
make install

# 3. Создать ветку
git checkout -b feature/my-feature

# 4. Внести изменения и тесты
# ...

# 5. Проверить качество
make all

# 6. Коммит и push
git commit -m "feat: add new feature"
git push origin feature/my-feature

# 7. Создать Pull Request
```

---

## 📊 Метрики проекта

### Размер кодовой базы

- **Исходный код:** ~2,110 строк
- **Тесты:** ~3,000+ строк
- **Документация:** ~5,000+ строк

### Покрытие тестами

- **Общее покрытие:** 39%
- **Основной функционал:** >80%
- **Критические части:** 100%

### Производительность

- **Тесты:** ~8 секунд (117 тестов)
- **Линтинг:** ~2 секунды
- **Type checking:** ~3 секунды

---

## 🎯 Основные выводы

### ✅ Сильные стороны

1. **Чистая архитектура** с разделением ответственности
2. **Гибкая конфигурация** через код и env переменные
3. **Хорошее покрытие тестами** критического функционала
4. **Современный стек** (FastAPI, SQLAlchemy 2.0, async)
5. **Подробная документация** на русском и английском
6. **Безопасность** на высоком уровне
7. **CI/CD** работает корректно
8. **i18n поддержка** из коробки

### 📈 Возможности для улучшения

1. **Увеличить покрытие тестами** (цель: >60%)
2. **Добавить больше языков** для i18n
3. **Документировать API** через OpenAPI более детально
4. **Добавить примеры** для PostgreSQL и MySQL
5. **Создать Docker Compose** примеры
6. **Улучшить документацию** для продакшн развёртывания

### 🔮 Перспективы развития

Проект находится в активной разработке и готов для использования в production. Основной функционал стабилен, архитектура продумана, безопасность на высоком уровне.

---

## 📞 Контакты и ресурсы

- **GitHub:** https://github.com/pydanny/fastapi-blog
- **PyPI:** https://pypi.org/project/fastapi-blog/
- **Документация:** См. `/docs` и корневые `.md` файлы
- **Примеры:** `tests/examples/`
- **Issues:** https://github.com/pydanny/fastapi-blog/issues

---

**Анализ выполнен:** 2026-05-15  
**Версия проекта:** 0.8.1+  
**Статус CI:** ✅ Passing

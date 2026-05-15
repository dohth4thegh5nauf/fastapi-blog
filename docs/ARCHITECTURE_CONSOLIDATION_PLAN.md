# План Консолидации Архитектуры

## Текущая Проблема

### Система 1: editor.py (Старая)
```
/api/posts/create/{slug}     - POST (REST API)
/api/posts/update/{slug}      - PUT
/api/posts/delete/{slug}      - DELETE
/api/posts/{slug}/raw         - GET
/api/posts/save/{slug}        - POST
/admin/editor/                - GET (UI список)
/admin/editor/new             - GET (UI создание)
/admin/editor/{slug}          - GET (UI редактирование)
```

### Система 2: admin/ (Новая)
```
/dashboard/                   - starlette-admin панель
/posts/list                   - Custom markdown list view
/posts/edit/{slug}            - Custom markdown edit view
/posts/new                    - Custom markdown create view
```

### Проблемы:
1. ❌ Дублирование функциональности
2. ❌ Две системы управления постами
3. ❌ Нет единой точки управления
4. ❌ Нет документации о совместном использовании
5. ❌ Путаница для пользователей

---

## Решение: Единая Админ-Панель

### Архитектура После Консолидации

```
┌─────────────────────────────────────────┐
│  FastAPI Application                    │
├─────────────────────────────────────────┤
│                                         │
│  /admin/  ──────────────────────────────┤── Starlette-Admin (единая точка)
│    ├── /user/list                      │   
│    ├── /user/create                    │   - User Management (SQLAlchemy)
│    ├── /user/edit/{id}                 │   - Post Management (Markdown Files)
│    ├── /post/list                      │   - Settings, Tags, etc.
│    ├── /post/create                    │   - i18n (RU/EN)
│    ├── /post/edit/{slug}               │   - Role-based permissions
│    └── /settings                       │   - Password hashing ✅
│                                         │
│  /api/  (опционально)                  │
│    └── /posts/*  ──────────────────────┤── REST API (для интеграций)
│                                         │   - Только если include_api=True
│  /  (публичный блог)                   │   - Требует аутентификацию
│    ├── /                               │
│    ├── /post/{slug}                    │   
│    └── /tag/{tag}                      │   
└─────────────────────────────────────────┘
```

---

## Детальный План Реализации

### Этап 1: Консолидация Admin UI ✅

**1.1. Удалить дублирующий UI из editor.py**
```python
# Удалить:
- /admin/editor/                # список постов
- /admin/editor/new             # создание
- /admin/editor/{slug}          # редактирование

# Оставить только REST API для программного доступа
```

**1.2. Улучшить starlette-admin views**
```python
# Вместо CustomView использовать полноценные ModelView:

class MarkdownPostView(ModelView):
    """View for managing markdown posts."""
    
    # Custom fields
    fields = [
        "slug",
        MarkdownField("content"),  # Rich markdown editor
        TagsField("tags"),
        DateTimeField("date"),
        "published"
    ]
    
    # Локализация
    label = "Posts"
    label_plural = "Posts"
    
    # Permissions
    def can_create(self, request: Request) -> bool:
        return "admin" in request.state.user.get("roles", [])
    
    def can_edit(self, request: Request) -> bool:
        return "admin" in request.state.user.get("roles", [])
    
    def can_delete(self, request: Request) -> bool:
        return "admin" in request.state.user.get("roles", [])
```

### Этап 2: Улучшение Аутентификации ✅

**2.1. Role-Based Access Control**
```python
class ImprovedAuthProvider(AuthProvider):
    """Enhanced auth with roles and permissions."""
    
    ROLES = {
        "admin": {
            "name": "Administrator",
            "permissions": ["create", "edit", "delete", "publish"]
        },
        "editor": {
            "name": "Editor",
            "permissions": ["create", "edit"]
        },
        "viewer": {
            "name": "Viewer", 
            "permissions": ["read"]
        }
    }
    
    async def login(self, username, password, ...):
        # Проверка пароля с bcrypt ✅
        if pwd_context.verify(password, user.hashed_password):
            request.session["user"] = username
            request.session["roles"] = user.roles
            return response
```

**2.2. Интеграция с User Model**
```python
# Связать SimpleAuthProvider с User модель из БД
# Вместо hardcoded credentials использовать реальных пользователей
```

### Этап 3: Интернационализация (i18n) 🆕

**3.1. Добавить поддержку языков**
```python
from starlette_admin.i18n import I18nConfig

admin = Admin(
    engine,
    title="FastAPI Blog Admin",
    i18n_config=I18nConfig(
        default_locale="en",
        language_switcher=["en", "ru"]
    )
)
```

**3.2. Создать файлы переводов**
```
locales/
  ├── en/
  │   └── LC_MESSAGES/
  │       ├── admin.po
  │       └── admin.mo
  └── ru/
      └── LC_MESSAGES/
          ├── admin.po
          └── admin.mo
```

**Основные строки для перевода:**
```
# English
"Posts" / "Посты"
"Create Post" / "Создать Пост"
"Edit Post" / "Редактировать Пост"
"Published" / "Опубликовано"
"Draft" / "Черновик"
"Save" / "Сохранить"
"Delete" / "Удалить"
"Settings" / "Настройки"
"Users" / "Пользователи"
"Logout" / "Выход"
```

### Этап 4: Custom Fields для Markdown 🆕

**4.1. MarkdownField с превью**
```python
from starlette_admin import BaseField

class MarkdownField(BaseField):
    """Rich markdown editor with live preview."""
    
    async def serialize_value(self, request, value, action):
        # Render markdown to HTML for preview
        return markdown.markdown(value)
    
    def additional_css_links(self, request):
        return [
            "https://cdn.jsdelivr.net/npm/easymde/dist/easymde.min.css"
        ]
    
    def additional_js_links(self, request):
        return [
            "https://cdn.jsdelivr.net/npm/easymde/dist/easymde.min.js"
        ]
```

**4.2. TagsField для категорий**
```python
class TagsField(BaseField):
    """Multi-select tags field."""
    
    render_function_key = "tags"
    
    async def serialize_value(self, request, value, action):
        return value.split(",") if isinstance(value, str) else value
```

### Этап 5: Опциональный REST API

**5.1. Сделать REST API опциональным**
```python
def add_blog_to_fastapi(
    app: FastAPI,
    include_api: bool = False,  # 🆕 новый параметр
    ...
):
    """Add blog functionality to FastAPI app.
    
    Args:
        include_api: Include REST API endpoints (default: False)
                     Set to True if you need programmatic access
    """
    # Всегда добавляем публичные routes
    app.include_router(get_blog_router(prefix=prefix))
    
    # REST API только если нужен
    if include_api:
        from .editor import get_api_router
        app.include_router(
            get_api_router(require_auth=True),
            prefix="/api"
        )
```

### Этап 6: Миграция Данных

**6.1. Создать MarkdownPost "виртуальную" модель**
```python
# Для starlette-admin нужен ORM-like интерфейс
# Но посты хранятся в markdown файлах

class MarkdownPost:
    """Virtual model for markdown posts."""
    
    def __init__(self, slug: str):
        self.slug = slug
        self._load_from_file()
    
    def _load_from_file(self):
        path = POSTS_DIR / f"{self.slug}.md"
        content = path.read_text()
        # Parse frontmatter
        self.frontmatter, self.content = parse_markdown(content)
    
    def save(self):
        # Write back to file
        markdown = format_markdown(self.frontmatter, self.content)
        path = POSTS_DIR / f"{self.slug}.md"
        path.write_text(markdown)
```

---

## Преимущества Новой Архитектуры

### ✅ Единая Точка Управления
- Один URL: `/admin/`
- Единый интерфейс для всего
- Консистентный UX

### ✅ Масштабируемость
- Легко добавлять новые модели
- Реиспользуемые компоненты
- Модульная архитектура

### ✅ Безопасность
- Централизованная аутентификация
- Role-based permissions
- Password hashing ✅

### ✅ Локализация
- Русский + Английский из коробки
- Легко добавить другие языки
- Консистентные переводы

### ✅ Developer Experience
- Понятная структура
- Меньше кода
- Лучше документация

---

## План Миграции

### Фаза 1: Подготовка (не ломаем существующее)
1. ✅ Создать новые улучшенные views
2. ✅ Добавить i18n поддержку
3. ✅ Создать custom fields
4. ✅ Написать тесты

### Фаза 2: Переход (с обратной совместимостью)
1. ⚠️ Пометить старый UI как deprecated
2. ⚠️ Добавить warnings при использовании /admin/editor
3. ⚠️ Документировать migration path

### Фаза 3: Удаление старого (breaking change)
1. ❌ Удалить /admin/editor UI
2. ✅ Оставить REST API как опциональный
3. ✅ Обновить документацию и примеры

---

## Пример Использования После Консолидации

```python
from fastapi import FastAPI
from fastapi_blog import add_blog_to_fastapi
from fastapi_blog.admin import add_admin_to_app

app = FastAPI()

# 1. Добавляем публичный блог
add_blog_to_fastapi(
    app,
    prefix="blog",
    include_api=False  # REST API не нужен
)

# 2. Добавляем админ-панель (единственная точка управления)
admin = add_admin_to_app(
    app,
    database_url="sqlite:///blog.db",
    admin_username="admin",
    admin_password="secure_password",
    secret_key="your-secret-key",
    i18n_locales=["en", "ru"],  # 🆕 i18n
    default_locale="ru"          # 🆕 по умолчанию русский
)

# Готово! Управление через /admin/
```

---

## Вопросы для Согласования

1. **Timing**: Когда начинать миграцию?
2. **Breaking Changes**: Допустимы ли breaking changes для v1.0?
3. **REST API**: Оставлять ли REST API вообще? Или удалить полностью?
4. **Языки**: Только RU/EN или добавить другие?
5. **Custom Fields**: Какие еще поля нужны кроме Markdown и Tags?

---

**Статус**: 📋 План готов к обсуждению  
**Оценка работ**: ~3-5 дней разработки  
**Breaking Changes**: Да (для /admin/editor UI)  
**Обратная совместимость**: Через deprecation warnings

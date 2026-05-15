# TODO — План разработки fastapi-blog

Версия пакета: 0.8.1  
Обновлено: 2026-05-15

---

## Этап 1 — Архитектура (следующий релиз)

### 1.1 — i18n для blog-роутов
**Приоритет:** средний  
**Описание:** Сейчас i18n работает только для `/admin/{locale}`. Blog (`/blog`) не параметризован по локали.

**Что нужно:**
- Провести аудит blog-шаблонов: выписать все хардкоженные строки
- Добавить namespace `blog` в YAML-файлы переводов
- Добавить параметр `locales: list[str] = ["en"]` в `add_blog_to_fastapi()`
- Тест: при `locales=["en","ru"]` blog отдаёт переведённые строки

**Критерий готовности:** blog реагирует на `Accept-Language` или URL-префикс.

---

### 1.2 — Унификация аутентификации (REST API + admin-сессия)
**Приоритет:** средний  
**Описание:** Admin использует cookie-сессию, `/api/posts` — отдельный механизм. Нет общего FastAPI dependency.

**Что нужно:**
- Создать dependency `get_current_user(request)` → `str | None` (проверяет сначала сессию, затем Authorization header)
- Переключить `api_require_auth=True` на этот dependency
- Тест: одни credentials работают через сессию и через `Authorization: Basic`

**Критерий готовности:** единый dependency, покрытый тестами.

---

## Этап 2 — Качество кода

### 2.1 — Сузить except в i18n.py
**Приоритет:** низкий  
**Файл:** `src/fastapi_blog/admin/i18n.py:86`  
**Описание:** Bandit B112 — голый `except Exception: continue`.

```python
# Текущий код:
except Exception:
    continue

# Целевой код:
except (ValueError, KeyError, FileNotFoundError) as e:
    logger.debug("Skipping locale %s: %s", locale, e)
    continue
```

**Критерий готовности:** `bandit -r src/` не выдаёт B112.

---

### 2.2 — Аннотировать nosec в fields.py и rbac_auth_provider.py
**Приоритет:** низкий  
**Файлы:** `src/fastapi_blog/admin/fields.py:71`, `src/fastapi_blog/admin/rbac_auth_provider.py:134`  
**Описание:** Bandit B704 и B105 — ложные срабатывания, подтверждённые проверкой.

```python
# fields.py:71
return Markup(markdown.markdown(Markup.escape(value)))  # nosec B704

# rbac_auth_provider.py:134
{"password": "Password must be at least 8 characters"}  # nosec B105
```

**Критерий готовности:** `bandit -r src/` — 0 issues.

---

## Этап 3 — Документация

### 3.1 — Обновить счётчик тестов в README
**Приоритет:** низкий  
**Описание:** README содержит "50+ tests", фактически 88 тестов.

**Заменить:**
```
🧪 Comprehensive test coverage (50+ tests)
```
на:
```
🧪 Comprehensive test coverage (88+ tests)
```

---

### 3.2 — Убрать пометку "NEW in v0.8.0" из README
**Приоритет:** низкий  
**Описание:** Секция "Admin Panel Features (NEW in v0.8.0)" устарела. Убрать "(NEW in v0.8.0)" из заголовка.

---

### 3.3 — Добавить setup_fastapi_blog() в README Basic Usage
**Приоритет:** низкий  
**Описание:** README показывает только `add_blog_to_fastapi()` + `add_admin_to_app()` раздельно. Unified facade `setup_fastapi_blog()` задокументирован только в "Recommended" секции, но не в "Basic Usage".

**Добавить в "Basic Usage" пример:**

```python
# Упрощённый вариант через единый фасад
import fastapi_blog
from fastapi import FastAPI

app = FastAPI()
fastapi_blog.setup_fastapi_blog(
    app,
    locales=["en", "ru"],
    enable_role_management=True,
)
```

---

## Этап 4 — Технический долг (долгосрочный)

### 4.1 — Удалить get-pip.py из корня репозитория
**Приоритет:** низкий  
**Описание:** `get-pip.py` (27918 строк) — стандартный PyPA installer, попавший в репозиторий случайно. Не является частью проекта.

```bash
git rm get-pip.py
echo "get-pip.py" >> .gitignore
```

---

### 4.2 — Очистить .git.bak из репозитория
**Приоритет:** низкий  
**Описание:** Директория `.git.bak` в корне — артефакт ручных операций с git. Не должна быть в публичном репозитории.

```bash
git rm -r .git.bak
echo ".git.bak" >> .gitignore
```

---

## Справка: что уже выполнено (не трогать)

Для контекста — все задачи ниже закрыты в коммитах `8fc8f10`–`9df68c0`:

- ✅ app.state identity bug в RoleModelView.is_accessible
- ✅ Тема на list/detail/create/edit страницах admin
- ✅ Deprecated параметры add_admin_to_app() удалены
- ✅ setup_fastapi_blog() unified facade создан
- ✅ Lifespan композиция исправлена
- ✅ print() с паролем заменены на logging
- ✅ Валидация weak secret_key
- ✅ .env.example создан
- ✅ Тесты на RBAC, template isolation, theme, password logging (88 total)
- ✅ README, QUICKSTART, CONTRIBUTING обновлены
- ✅ changelog.md структурирован
- ✅ Firebase secrets проверены — чисто

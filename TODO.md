# TODO — План разработки fastapi-blog

Версия пакета: 0.8.1  
Обновлено: 2026-05-15

---

## Этап 1 — Архитектура (следующий релиз)

### 1.1 — i18n для blog-роутов ✅
**Статус:** Выполнено в коммите 297f00f  
**Реализовано:**
- ✅ Аудит blog-шаблонов завершён
- ✅ Добавлен namespace `blog` в en.yaml и ru.yaml
- ✅ Параметры `locales` и `default_locale` добавлены в `add_blog_to_fastapi()`
- ✅ Blog реагирует на Accept-Language header
- ✅ 10 новых тестов для i18n (98 passed total)

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



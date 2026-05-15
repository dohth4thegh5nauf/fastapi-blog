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

### 1.2 — Унификация аутентификации (REST API + admin-сессия) ✅
**Статус:** Выполнено в коммитах 24484b0, 5ecd08b  
**Реализовано:**
- ✅ Создан модуль `auth.py` с `get_current_user()` и `require_current_user()`
- ✅ Dependency проверяет session cookie, затем Authorization: Basic
- ✅ REST API использует unified auth при наличии credentials
- ✅ 9 новых тестов для unified auth (107 passed total)
- ✅ Одинаковые credentials работают через оба механизма

---

## Завершено

Все задачи Этапа 1 (Архитектура) выполнены.



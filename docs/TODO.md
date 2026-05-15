# Техническое задание: устранение технического долга fastapi-blog

**Репозиторий:** vampire-erotique/l5queic5diiu2eek  
**Дата первичного анализа:** 2026-05-15  
**Дата актуализации:** 2026-05-15 (ревизия после коммитов `4393ad8`–`80e1fa0`)  
**Источники:** `__init__.py` admin-модуля, тесты `test_role_management_access.py`,
`test_admin_template_isolation.py`, `git log --oneline -20`, `git diff HEAD~5 --stat`

---

## Что изменилось с первой версии ТЗ

### Закрыто (удалено из задач)

| Была задача | Коммиты | Подтверждение |
|---|---|---|
| 1.1 — app.state identity bug | `8fc8f10`, `3628be5` | `admin_username` передаётся напрямую в конструктор views, не через `app.state` |
| 1.2 — тема не наследуется | `3d2bcf7`, `d73da78`, `d269a3a` | кастомные шаблоны (`list.html`, `detail.html`, `create.html`, `edit.html`), `base.html` в `layouts/`, коммит явно называется "add theme switcher to ModelView pages" |
| 1.3 — multiprocess app.state | решена вместе с 1.1 | `app.state` больше не используется как канал передачи `admin_username` |
| 3.2 — нет тестов на RBAC | `4cf4208`, `cc90aab` | `test_role_management_access.py` — 8 тестов на `is_accessible`, доступность dropdown, локализацию меток |
| 3.2 — нет тестов на template isolation | `570ea5a`, `b8344f1` | `test_admin_template_isolation.py` — 3 теста на изоляцию шаблонов |

### Появилось новое (добавлено в задачи)

- `enable_role_management` — новый флаг с deprecated-параметрами (`i18n_enabled`, `base_url`, `i18n_locales`, `i18n_default_locale`) требует отдельной задачи по зачистке
- `firebase_config_added` (коммит `80e1fa0`, HEAD) — конфиг Firebase добавлен в репо; неясно, это prod-конфиг с секретами или заглушка — требует проверки
- `test_role_view_accessible_only_for_root_user` использует `Mock(spec=Request)` с `request.app.state.admin_username` — это противоречит исправлению 1.1: тест проверяет `app.state`, а views теперь читают напрямую из `self.admin_username`. Тест может давать ложноположительный результат
- `partials/` в шаблонах — директория создана, но содержимое не передано; статус неизвестен

---

## Этап 1 — Новые критические проблемы

---

## Этап 1 — Критические проблемы (требуют немедленного решения)

### Задача 1.1 — Проверить и устранить утечку секретов в firebase_config_added

**Проблема.**  
Последний коммит `80e1fa0 firebase_config_added` добавляет конфигурацию Firebase в репозиторий.
Публичный репозиторий + Firebase config = потенциальная утечка API-ключей, project ID,
и других credentials, которые могут использоваться для несанкционированного доступа к
Firebase-проекту.

**Что сделать агенту.**

1. Найти добавленные файлы: `git show 80e1fa0 --stat` и `git show 80e1fa0`.
2. Проверить, содержат ли файлы реальные секреты (`apiKey`, `authDomain`, `databaseURL`,
   `storageBucket`, service account JSON) или только заглушки-placeholders.
3. Если реальные секреты — немедленно:
   a. Отозвать скомпрометированные ключи в Firebase Console.
   b. Удалить файл из истории: `git filter-repo --path firebase_config.json --invert-paths`.
   c. Force-push в удалённый репозиторий.
   d. Добавить паттерн в `.gitignore`: `*firebase*config*`, `service-account*.json`.
5. Добавить `gitleaks` или `trufflehog` в CI (`.github/workflows/`) для автоматической
   проверки на утечки секретов в каждом PR.

**Критерий готовности:** `git show 80e1fa0` не содержит реальных API-ключей; CI блокирует
коммиты с секретами.

Если нет текущих утечек, тогда нужно просто тестировать эту директорию в CI с особым контролем.

---

### Задача 1.2 — Исправить ложноположительный тест test_role_view_accessible_only_for_root_user

**Проблема.**  
Тест в `test_role_management_access.py` делает:
```python
request = Mock(spec=Request)
request.app.state.admin_username = "admin"
```
Но исправление `8fc8f10` перевело `views_role.py` на хранение `admin_username` как атрибута
экземпляра view (`self.admin_username`), а не на чтение из `request.app.state`.
Тест настраивает `request.app.state`, которое view уже не читает — тест проходит не потому
что логика верна, а потому что Mock позволяет установить любой атрибут без проверки.

**Что сделать агенту.**

1. Прочитать актуальную реализацию `is_accessible` в `views_role.py` и убедиться,
   откуда она читает `admin_username` — из `self` или из `request.app.state`.
2. Переписать setup-часть теста под реальный контракт:
   ```python
   # Если view хранит admin_username в self:
   role_view = RoleModelView(Role, locale="en", admin_username="admin")
   request = Mock(spec=Request)
   request.session = {"user": "admin"}
   assert role_view.is_accessible(request) is True
   ```
3. Убрать `request.app.state.admin_username = "admin"` из всех тестов, где это
   не соответствует реальной реализации.
4. Добавить тест, который явно проверяет, что `request.app.state` НЕ используется:
   ```python
   def test_is_accessible_does_not_use_app_state():
       view = RoleModelView(Role, locale="en", admin_username="admin")
       request = Mock(spec=Request)
       request.session = {"user": "admin"}
       # Намеренно не устанавливаем request.app.state
       del request.app  # если view обратится к app — AttributeError
       assert view.is_accessible(request) is True
   ```

**Критерий готовности:** тесты проходят, и при этом проверяют реальный контракт view,
а не артефакт Mock.

---

## Этап 2 — Архитектурный долг

### Задача 2.1 — Зачистить deprecated-параметры add_admin_to_app

**Проблема.**  
`add_admin_to_app` накопил четыре deprecated-параметра: `base_url`, `i18n_enabled`,
`i18n_default_locale`, `i18n_locales`. Они принимаются, генерируют `warnings.warn`, и
игнорируются. Это увеличивает cognitive load, затрудняет рефакторинг, и создаёт
ложное ощущение обратной совместимости там, где поведение уже изменилось необратимо.

Дополнительно: `test_admin_template_isolation.py` всё ещё передаёт `i18n_enabled=False`
в fixture `app_with_admin` — значит тест написан под старый API и проверяет несуществующее
поведение.

**Что сделать агенту.**

1. Определить версию для удаления deprecated-параметров (например, v0.9.0) и зафиксировать
   в docstring: `.. deprecated:: 0.8.0 — будет удалено в 0.9.0`.
2. Исправить `test_admin_template_isolation.py`: убрать `i18n_enabled=False`,
   привести fixture к текущему API:
   ```python
   @pytest.fixture
   def app_with_admin():
       app = FastAPI()
       admins = fastapi_blog.add_admin_to_app(
           app,
           title="Test Admin",
           admin_username="admin",
           admin_password="Admin123!",
           secret_key="test-secret-key",
           locales=["en"],        # вместо i18n_enabled=False
           default_locale="en",
       )
       return app, admins
   ```
3. Добавить тест на `DeprecationWarning`:
   ```python
   def test_deprecated_i18n_locales_warns():
       app = FastAPI()
       with pytest.warns(DeprecationWarning, match="i18n_locales is deprecated"):
           fastapi_blog.add_admin_to_app(app, ..., i18n_locales=["en"])
   ```
4. Создать `CHANGELOG` запись о плане удаления.

**Критерий готовности:** все тесты используют актуальный API; deprecated-параметры помечены
с версией удаления; тест на `DeprecationWarning` добавлен.

---

### Задача 2.2 — Унифицировать точки входа add_blog_to_fastapi и add_admin_to_app

**Проблема.**  
Две публичные функции инициализации независимы, порядок их вызова нигде не валидируется.
`add_admin_to_app` не знает, был ли вызван `add_blog_to_fastapi` до неё. При этом
lifespan-контекст в `add_admin_to_app` перезаписывает router.lifespan_context напрямую,
что потенциально конфликтует с lifespan приложения пользователя.

**Что сделать агенту.**

1. Ввести опциональный единый фасад `setup_fastapi_blog`:
   ```python
   def setup_fastapi_blog(
       app: FastAPI,
       *,
       posts_dir: str = "posts",
       include_api: bool = False,
       locales: list[str] = ["en"],
       default_locale: str = "en",
       admin_username: str | None = None,
       admin_password: str | None = None,
       secret_key: str | None = None,
       enable_role_management: bool = False,
   ) -> dict[str, Admin]: ...
   ```
2. Исправить перезапись `router.lifespan_context`: вместо замены — композировать через
   `asynccontextmanager` chain, чтобы пользовательский lifespan сохранялся:
   ```python
   # Неправильно: app.router.lifespan_context = admin_lifespan
   # Правильно: обернуть существующий lifespan
   ```
3. Добавить интеграционный тест: приложение с собственным lifespan + `add_admin_to_app`
   — оба lifespan выполняются при старте.

**Критерий готовности:** `setup_fastapi_blog` работает; пользовательский lifespan не
перезаписывается; тест на композицию lifespan добавлен.

---

### Задача 2.3 — Распространить i18n на blog-роуты и шаблоны

**Проблема.**  
i18n реализована для `/admin/{locale}` через отдельные экземпляры Admin и YAML-переводы.
Blog (`/blog`) — только английский, шаблоны и строки не параметризованы. Архитектура
перевода в admin (YAML + `load_translations`) существует, но не переиспользуется в blog-части.

**Что сделать агенту.**

1. Провести аудит blog-шаблонов: выписать все хардкоженные строки
   ("Tags", "Read more", "Posted on", даты и т.д.).
2. Переиспользовать существующую `load_translations` / `get_all_locale_names` инфраструктуру:
   добавить namespace `blog` в YAML-файлы переводов.
3. Добавить параметр `locales: list[str] = ["en"]` в `add_blog_to_fastapi`, передавать
   locale в Jinja2 context через middleware или dependency.
4. Обновить документацию с примером.

**Критерий готовности:** при `locales=["en", "ru"]` blog отдаёт переведённые строки;
переводы хранятся в том же месте, что и admin-переводы.

---

### Задача 2.4 — Унифицировать аутентификацию между admin-сессией и REST API

**Проблема.**  
Admin использует cookie-сессию (`SessionMiddleware`), `/api/posts` — отдельный механизм
(HTTP Basic или bearer — из кода `__init__.py` неясно). Нет общего dependency, который
работал бы для обоих путей. `SimpleAuthProvider` знает о сессии, но не о REST-запросах.

**Что сделать агенту.**

1. Создать FastAPI dependency `get_current_user(request: Request) -> str | None`:
   ```python
   async def get_current_user(request: Request) -> str | None:
       # Сначала сессия (admin UI)
       if user := request.session.get("user"):
           return user
       # Затем Authorization header (REST API)
       if auth := request.headers.get("Authorization"):
           ...
       return None
   ```
2. Переключить `api_require_auth=True` на этот dependency.
3. Написать тест: одни и те же credentials работают через сессионный логин и через
   `Authorization: Basic`.

**Критерий готовности:** единый dependency, покрытый тестами для обоих путей аутентификации.

---

## Этап 3 — Качество кода и тестирование

### Задача 3.1 — Убрать print-логи из add_admin_to_app

**Проблема.**  
В `__init__.py` admin-модуля `add_admin_to_app` содержит серию `print()` вызовов,
которые выполняются при каждом старте приложения:
```
✓ Admin panel (en) mounted at /admin/en
✓ Login: username='admin' password='Admin123!'
✓ Available locales: en, ru
```
Третья строка — информационная утечка: пароль выводится в stdout в любом окружении,
включая production. Debug-логи (`[DEBUG] app id: ...`) из коммита `9332be8` к этому моменту
должны быть убраны, но `print("✓ Login: ...")` — нет.

**Что сделать агенту.**

1. Заменить все `print(...)` в `add_admin_to_app` и `_create_admin_for_locale` на
   `logger.info(...)` / `logger.debug(...)` с именованным логгером:
   ```python
   import logging
   logger = logging.getLogger("fastapi_blog.admin")
   ```
2. Строку с паролем перевести на `logger.debug` — она нужна только при отладке:
   ```python
   logger.debug("Admin credentials: username=%s", admin_username)
   # пароль — никогда не логировать даже в debug
   ```
3. В `demo.sh` добавить явный `LOG_LEVEL=DEBUG` чтобы при демо вывод сохранялся,
   но в prod молчал.
4. Добавить тест: `caplog` не содержит пароль при уровне INFO:
   ```python
   def test_password_not_logged_at_info(caplog):
       with caplog.at_level(logging.INFO, logger="fastapi_blog.admin"):
           fastapi_blog.add_admin_to_app(app, admin_password="SuperSecret!")
       assert "SuperSecret!" not in caplog.text
   ```

**Критерий готовности:** `./demo.sh` без `LOG_LEVEL=DEBUG` не выводит пароль в stdout.

---

### Задача 3.2 — Добавить тесты на тему (theme switcher)

**Проблема.**  
`grep -r "theme\|dark\|light\|switcher" tests/ --include="*.py" -l` возвращает только
`tests/examples/admin_full_featured.py` и `tests/examples/admin_i18n.py` — это примеры
использования, не unit/integration тесты. Переключатель темы реализован в коммите `3d2bcf7`,
но не покрыт тестами. Регрессия незаметна до ручной проверки.

**Что сделать агенту.**

Создать `tests/test_admin_theme.py` со следующими тестами:

| Тест | Что проверяет |
|---|---|
| `test_theme_template_exists` | файл `partials/theme_switcher.html` (или аналог) существует |
| `test_list_template_extends_base` | `list.html` содержит `{% extends` на `base.html` |
| `test_detail_template_extends_base` | `detail.html` содержит `{% extends` на `base.html` |
| `test_create_template_extends_base` | `create.html` содержит `{% extends` на `base.html` |
| `test_edit_template_extends_base` | `edit.html` содержит `{% extends` на `base.html` |
| `test_base_html_contains_theme_block` | `layouts/base.html` содержит блок или include переключателя |

Шаблон теста на наследование:
```python
from pathlib import Path
import fastapi_blog

def test_list_template_extends_base():
    pkg = Path(fastapi_blog.__file__).parent
    template = (pkg / "admin" / "templates" / "list.html").read_text()
    assert '{% extends' in template
    assert 'base.html' in template
```

**Критерий готовности:** 6 тестов добавлены и проходят; `make test` включает их в coverage.

---

### Задача 3.3 — Ужесточить безопасность defaults

**Проблема.**  
`add_admin_to_app` принимает `secret_key` с дефолтом
`"change-me-in-production-please-use-strong-secret"` (38 символов, но предсказуемый).
Нет валидации энтропии. `test_password_validation.py` существует — значит валидация пароля
уже частично реализована, но конфиг secret_key не защищён аналогично.

**Что сделать агенту.**

1. Проверить содержимое `test_password_validation.py` и убедиться, что тест покрывает
   слабые пароли в `admin_password`.
2. Добавить валидацию `secret_key` в `add_admin_to_app`:
   ```python
   WEAK_SECRETS = {"change-me-in-production-please-use-strong-secret", "changeme", "secret", ""}
   if secret_key in WEAK_SECRETS or len(secret_key) < 32:
       import warnings
       warnings.warn(
           "secret_key слабый или дефолтный. Используйте secrets.token_hex(32) для production.",
           UserWarning, stacklevel=2,
       )
   ```
   (предупреждение, не ошибка — чтобы не ломать demo.sh)
3. Добавить `.env.example` в корень:
   ```
   FASTAPI_BLOG_ADMIN_LOGIN=admin
   FASTAPI_BLOG_ADMIN_PASSWORD=changeme
   SECRET_KEY=  # сгенерируйте: python -c "import secrets; print(secrets.token_hex(32))"
   DATABASE_URL=sqlite:///./blog.db
   ```
4. Добавить в `.gitignore`: `.env`, `*.env.local`.
5. Добавить тест:
   ```python
   def test_weak_secret_key_warns():
       app = FastAPI()
       with pytest.warns(UserWarning, match="secret_key"):
           fastapi_blog.add_admin_to_app(app, secret_key="short")
   ```

**Критерий готовности:** слабый `secret_key` генерирует `UserWarning`; `.env.example` добавлен.

---

## Этап 4 — Документация и Developer Experience

### Задача 4.1 — Синхронизировать README с реальным репозиторием и новым API

**Проблема.**  
README содержит `git clone https://github.com/awestley/fastapi-blog.git` (старый репо).
Примеры кода используют старый API без `locales`, `default_locale`, `enable_role_management`.
Раздел "Admin Panel Features" упоминает v0.8.0 как "NEW", хотя код уже значительно вырос.

**Что сделать агенту.**

1. Заменить все ссылки на `awestley/fastapi-blog` на актуальные.
2. Обновить примеры кода в README под текущий API:
   ```python
   fastapi_blog.add_admin_to_app(
       app,
       locales=["en", "ru"],
       default_locale="en",
       enable_role_management=True,
   )
   ```
3. Добавить секцию "Role Management" с описанием `enable_role_management=True`.
4. Убрать пометку "NEW in v0.8.0" — это теперь просто фича, не новинка.
5. Проверить все URLs в README скриптом (`python -m http` или `curl -s -o /dev/null -w "%{http_code}"`).

**Критерий готовности:** все ссылки рабочие; примеры кода соответствуют текущему API.

---

### Задача 4.2 — Актуализировать QUICKSTART.md

**Проблема.**  
QUICKSTART описывает `make install` без альтернатив. Firebase-конфиг добавлен в репо,
но в QUICKSTART нет упоминания о необходимых env-переменных. Нет секции для role management.

**Что сделать агенту.**

1. Добавить секцию Prerequisites:
   ```
   ## Требования
   - Python 3.12+
   - uv (https://docs.astral.sh/uv/) или pip
   - Git
   ```
2. Добавить альтернативный путь без uv:
   ```bash
   python -m venv venv && source venv/bin/activate
   pip install -e ".[dev]"
   ```
3. Добавить секцию Environment Variables с отсылкой на `.env.example`.
4. Добавить `docker-compose.yml` для one-command запуска:
   ```yaml
   services:
     blog:
       build: .
       ports: ["8000:8000"]
       env_file: .env
   ```
5. Добавить секцию "Role Management Quickstart" с примером `enable_role_management=True`.

**Критерий готовности:** новый разработчик запускает проект по QUICKSTART без обращения к Google.

---

### Задача 4.3 — Структурировать changelog и добавить CONTRIBUTING.md

**Проблема.**  
Нет `CONTRIBUTING.md`. Неизвестно, структурирован ли `changelog.md`.
133 коммита в `main` — без структурированного changelog сложно понять историю проекта.

**Что сделать агенту.**

1. Привести `changelog.md` к формату [Keep a Changelog](https://keepachangelog.com/):
   ```markdown
   ## [Unreleased]
   ### Added
   - Role management with RBAC (enable_role_management parameter)
   - Theme switcher on all admin ModelView pages
   ### Fixed
   - app.state identity bug in RoleModelView.is_accessible
   - Admin template isolation from public blog templates
   ### Deprecated
   - i18n_enabled, i18n_locales, i18n_default_locale, base_url parameters
     (будут удалены в v0.9.0)
   ```
2. Создать `CONTRIBUTING.md`:
   - как запустить тесты (`make test`, `make lint`)
   - code style (ruff, mypy)
   - процесс PR и ветвления
   - как добавить новую локаль (добавить YAML в translations/, обновить `get_all_locale_names`)
   - как добавить новый ModelView
3. Создать `docs/migration_v08.md` с инструкцией перехода с blog-only на blog+admin,
   включая секцию о новых параметрах и deprecated-параметрах.

**Критерий готовности:** `CONTRIBUTING.md` создан; `changelog.md` структурирован;
migration guide охватывает изменения API.

---

## Порядок выполнения для агента

```
Этап 1 (новые критические) — в первую очередь, последовательно:
  1.1 (Firebase secrets) → 1.2 (исправить тест)
  После 1.1: make test убеждается, что тесты не упали

Этап 2 (архитектура) — после Этапа 1:
  2.1 (deprecated API cleanup) → 2.2 (unified entry point) → 2.3 (blog i18n) → 2.4 (unified auth)
  2.1 является prerequisite для 2.2: нужно сначала зафиксировать API

Этап 3 (качество) — параллельно с Этапом 2:
  3.1 (убрать print) — независимо, быстро
  3.2 (тесты на тему) — после 3.1
  3.3 (безопасность defaults) — независимо

Этап 4 (документация) — в последнюю очередь, когда API стабилен:
  4.1 → 4.2 → 4.3
```

---

## Метрики приёмки

| Метрика | Статус | Цель |
|---|---|---|
| `/admin/en/role/list` → 200 для admin | ✅ закрыто (8fc8f10) | — |
| Тема на list-страницах | ✅ закрыто (3d2bcf7) | — |
| `[DEBUG]` строки с id процессов в stdout | ✅ закрыто (9332be8→8fc8f10) | — |
| Тесты на RBAC и template isolation | ✅ закрыто (8 + 3 теста) | — |
| Firebase-конфиг не содержит реальных секретов | ❓ не проверено | ✅ проверено и зачищено |
| Тест `test_role_view_accessible_only_for_root_user` проверяет реальный контракт | ❌ использует Mock с app.state | ✅ исправлен |
| Deprecated-параметры помечены с версией удаления | ❌ только `warnings.warn` | ✅ версия в docstring |
| `print("✓ Login: username=... password=...")` убрана из stdout | ❌ есть в коде | ✅ нет |
| Тесты на theme switcher (не только examples) | ❌ нет unit-тестов | ✅ 6 тестов |
| Слабый `secret_key` генерирует предупреждение | ❌ не валидируется | ✅ `UserWarning` |
| `.env.example` в репозитории | ❌ нет | ✅ есть |
| Все ссылки в README рабочие | ❌ awestley/ | ✅ актуальные |
| `docker compose up` → работающий блог | ❌ нет compose | ✅ есть |
| `CONTRIBUTING.md` | ❌ нет | ✅ есть |
| `changelog.md` структурирован | ❓ неизвестно | ✅ Keep a Changelog |

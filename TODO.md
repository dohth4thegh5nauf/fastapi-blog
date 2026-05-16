https://github.com/tanstaaflayenani/egheixa3bohkooe1

---

проблема ссылок боковой панели, которые ведут только на английскую локаль. попрежнему редиректит на английскую версию. а точнее в ссылках изначально дефолтная локаль без префикса

---

Как именно вы запускаете приложение? ./demo.sh
Какой URL вы открываете в браузере? http://localhost:8000/ru/admin/
На какую ссылку кликаете? любая из бокового меню

---

рендер навигации:

```html
<div class="collapse navbar-collapse" id="sidebar-menu">
                        <ul class="navbar-nav pt-lg-3">
                            
                                
                                    <li class="nav-item">
        <a class="nav-link " href="http://localhost:8000/admin/">
            
                <span class="nav-link-icon d-md-none d-lg-inline-block">
                    <i class="fa fa-home"></i>
                </span>
            
            <span class="nav-link-title">Home</span>
        </a>
    </li>

                                
                            
                                
                                    <li class="nav-item">
        <a class="nav-link " href="http://localhost:8000/admin/user/list">
            
                <span class="nav-link-icon d-md-none d-lg-inline-block">
                    <i class="fa fa-users"></i>
                </span>
            
            <span class="nav-link-title">Users</span>
        </a>
    </li>

                                
                            
                                
                                    <li class="nav-item dropdown active">
        <a class="nav-link dropdown-toggle show" href="#" data-bs-toggle="dropdown" role="button">
            
                <span class="nav-link-icon d-md-none d-lg-inline-block">
                    <i class="fa fa-shield"></i>
                </span>
            
            <span class="nav-link-title">Access Control</span>
        </a>
        <div class="dropdown-menu show">
            <div class="dropdown-menu-columns">
                <div class="dropdown-menu-column">
                    
                        
                            <a href="http://localhost:8000/admin/role/list" class="dropdown-item">Roles</a>
                        
                    
                        
                            <a href="http://localhost:8000/admin/user_with_roles/list" class="dropdown-item active fw-bold ">User Roles</a>
                        
                    
                </div>
            </div>
        </div>
    </li>

                                
                            
                                
                                    <li class="nav-item">
        <a class="nav-link " href="http://localhost:8000/admin/posts/list">
            
                <span class="nav-link-icon d-md-none d-lg-inline-block">
                    <i class="fa fa-file-text"></i>
                </span>
            
            <span class="nav-link-title">Posts</span>
        </a>
    </li>

                                
                            
                                
                            
                                
                            
                            
                        </ul>
                    </div>
```

---

Вот оно! Нашёл проблему! Смотрите внимательно на HTML который вы показали:

```html
<a class="nav-link " href="http://localhost:8000/admin/">  <!-- ❌ без /ru/ -->
<a class="nav-link " href="http://localhost:8000/admin/user/list">  <!-- ❌ без /ru/ -->
<a href="http://localhost:8000/admin/role/list" class="dropdown-item">  <!-- ❌ без /ru/ -->
<a class="nav-link " href="http://localhost:8000/admin/posts/list">  <!-- ❌ без /ru/ -->
```

Вы на странице `/admin/ru/...`, но все ссылки в sidebar ведут на `/admin/...` (без `/ru/`). Это проблема в **starlette-admin** библиотеке, которая генерирует эти ссылки.

Проблема не в blog шаблонах (они правильные), а в том как starlette-admin генерирует навигацию. Это генерируется самой библиотекой starlette-admin.

Каждый admin монтируется по своему пути (`/admin` для default, `/ru/admin` для ru), но **starlette-admin не знает о других локалях** и генерирует ссылки без учёта текущей локали.

Проблема в том, что когда мы создаём admin instance с `base_url="/ru/admin"`, starlette-admin должен использовать этот base_url для всех ссылок, но похоже он этого не делает корректно, или наша конфигурация неправильная...

---

https://github.com/tanstaaflayenani/egheixa3bohkooe1/commit/8358fc82c3551acaa35a0e275eb3eaabe58fb476

---

**Диагноз:** Коммит `8358fc8` правильно добавил `admin_base_url` в глобалы Jinja и использовал его в `layout.html` для брендовой ссылки и кнопок Logout. Но ссылки в сайдбаре (`Home`, `Users`, `Posts`, и т.д.) генерируются через `macros/views.html` — а этот макрос использует `view.url(request)`, который starlette-admin вычисляет на основе `request.url_for(...)` без учёта нашего `base_url`. Поэтому ссылки всё равно ведут на `/admin/...` вместо `/ru/admin/...`.

**Решение:** Нужно переопределить `macros/views.html`, чтобы ссылки строились через `admin_base_url` + относительный путь view, а не через `view.url(request)`. Вот что именно нужно сделать:

**1. В `src/fastapi_blog/admin/templates/macros/views.html`** — перехватить генерацию URL.

Сначала нужно понять, что именно отдаёт `view.url(request)`. Starlette-admin формирует URL через `request.url_for(route_name)`, который не знает о вашем locale-префиксе. Самый надёжный способ — переписать URL в макросах, заменяя дефолтный base_url на `admin_base_url`.

Вот конкретный подход — добавить Jinja2-фильтр или глобальную функцию, которая делает замену:

```python
# В _create_admin_for_locale(), после добавления admin_base_url:
default_base_url = "/admin"  # базовый URL starlette-admin по умолчанию (без локали)

def fix_url(url: str) -> str:
    """Заменяет дефолтный /admin на /ru/admin в ссылках."""
    if url and url.startswith(default_base_url):
        return base_url + url[len(default_base_url):]
    return url

admin.templates.env.globals["fix_url"] = fix_url
admin.templates.env.globals["admin_base_url"] = base_url
```

Но проблема в том, что нет гарантии, что `default_base_url` всегда `/admin`. Лучше вычислить его из самого admin-объекта.

**Правильнее:** посмотреть, что именно генерирует `view.url(request)` и из чего оно состоит. Судя по исходникам starlette-admin, URL строится как `{base_url}/{view.identity}/list` (для model views). Значит можно переопределить макросы, используя `admin_base_url`:

**`src/fastapi_blog/admin/templates/macros/views.html`** должен выглядеть примерно так:

```jinja2
{% macro model_link(view) %}
{% set url = admin_base_url + "/" + view.identity + "/list" %}
<li class="nav-item {% if request.url.path.startswith(admin_base_url + "/" + view.identity) %}active{% endif %}">
    <a class="nav-link {% if request.url.path.startswith(admin_base_url + "/" + view.identity) %}active{% endif %}"
       href="{{ url }}">
        {% if view.icon %}
        <span class="nav-link-icon d-md-none d-lg-inline-block">
            <i class="{{ view.icon }}"></i>
        </span>
        {% endif %}
        <span class="nav-link-title">{{ view.label }}</span>
    </a>
</li>
{% endmacro %}
```

**Но есть более чистый способ** — добавить в Python глобальную функцию `url_for_view`:

```python
# в _create_admin_for_locale():
def url_for_view(view_identity: str, action: str = "list") -> str:
    return f"{base_url}/{view_identity}/{action}"

admin.templates.env.globals["url_for_view"] = url_for_view
```

А затем в `macros/views.html` использовать её вместо `view.url(request)`.

---

**Но самый простой способ** (без глубокого переписывания макросов) — добавить строковую замену через фильтр:

В `__init__.py`, в `_create_admin_for_locale`:

```python
# Определяем дефолтный base_url starlette-admin (он всегда /admin для default locale)
# Нам нужно получить его из admin объекта до того, как мы переопределяем
_starlette_base_url = admin.base_path  # или admin._base_url — зависит от версии

def rebase_url(url: str) -> str:
    if url and _starlette_base_url and url.startswith(_starlette_base_url):
        return base_url + url[len(_starlette_base_url):]
    return url

admin.templates.env.filters["rebase_url"] = rebase_url
admin.templates.env.globals["admin_base_url"] = base_url
```

И в `macros/views.html` заменить `view.url(request)` на `view.url(request) | rebase_url`.

---

**Итог — что конкретно делать:**

Посмотрите на атрибут admin-объекта, где хранится base_url. В starlette-admin это обычно `admin.base_url` или `admin._base_url`. Проверьте это в исходниках или через `print(dir(admin))`. Затем:

1. В `_create_admin_for_locale()` добавьте фильтр `rebase_url` (как выше).
2. Скопируйте оригинальный `@starlette-admin/macros/views.html` в ваш `templates/macros/views.html`.
3. Замените все `view.url(request)` на `view.url(request) | rebase_url` в скопированном файле.

Это гарантирует, что все nav-ссылки будут содержать правильный locale-префикс, при этом минимально расходясь от апстрима starlette-admin.

---

# ТЗ: Исправление ссылок сайдбара в локализованном admin

## Контекст и суть проблемы

Коммит `8358fc8` ("deluge") начал работу: добавил `admin_base_url` в глобалы Jinja и переопределил `layout.html`, чтобы логотип и кнопка Logout правильно ссылались на `/ru/admin`. Но ссылки в навигации (Home, Users, Posts и т.д.) по-прежнему ведут на `/admin/...` — потому что они генерируются макросами `macros/views.html`, который вызывает `view.url(request)`. Этот метод внутри starlette-admin строит URL через `request.url_for(route_name)`, а роутер смонтирован под именем, которое соответствует дефолтному `/admin` пути — независимо от того, какой `base_url` мы передали.

---

## Задача 1 — Исправить ссылки в `macros/views.html` (основная проблема)

**Файл:** `src/fastapi_blog/admin/templates/macros/views.html`

Этот файл уже скопирован из starlette-admin в коммите (судя по дереву). Нужно найти в нём все места, где используется `view.url(request)`, и заменить на корректно построенный URL.

**Механизм:** В starlette-admin `view.url(request)` возвращает результат `request.url_for(view._url_name)`. Проблема в том, что `url_for` работает с именованными роутами, и имена роутов у ru-admin и en-admin разные (они уникализируются через mount-имя). Поэтому нужно либо:

**Вариант A (рекомендуется) — фильтр `rebase_url`:**

В `src/fastapi_blog/admin/__init__.py`, в функции `_create_admin_for_locale`, после строки с `admin_base_url` добавить:

```python
# Получаем дефолтный base_path starlette-admin
# (это путь, относительно которого он строит url_for)
_sa_base = admin.base_path  # проверить атрибут: может быть base_path, _base_url, base_url

def rebase_url(url: str) -> str:
    """Заменяет дефолтный prefix starlette-admin на наш locale-специфичный."""
    if url and isinstance(url, str) and url.startswith(_sa_base):
        return base_url + url[len(_sa_base):]
    return url

admin.templates.env.filters["rebase_url"] = rebase_url
```

Затем в `macros/views.html` заменить все вхождения `view.url(request)` на `view.url(request) | rebase_url`.

**Вариант B — глобальная функция `view_url`:**

```python
def view_url(view, request) -> str:
    raw = view.url(request)
    if raw and raw.startswith(_sa_base):
        return base_url + raw[len(_sa_base):]
    return raw

admin.templates.env.globals["view_url"] = view_url
```

И в макросах использовать `view_url(view, request)` вместо `view.url(request)`.

**Что проверить перед реализацией:**
- Как именно называется атрибут base_url в объекте `admin` — запустить `print(dir(admin))` или посмотреть исходник `starlette_admin/base.py`. Скорее всего это `admin.base_path` или `admin._base_url`.
- Посмотреть текущий `macros/views.html` в репо — что именно там вызывается для каждого типа view (`model_link`, `custom_link`, `dropdown_link`).

**Acceptance criteria:** При нахождении на `/ru/admin/...` все ссылки в сайдбаре ведут на `/ru/admin/...`. При нахождении на `/admin/...` (en) — на `/admin/...`.

---

## Задача 2 — Исправить активное состояние ссылок в сайдбаре

**Проблема:** Макросы starlette-admin определяют активный пункт меню, сравнивая `request.url.path` с `view.url(request)`. После rebase_url ссылки станут правильными, но проверка активности тоже нуждается в починке, иначе ни один пункт не будет подсвечиваться как активный.

**Решение:** В `macros/views.html` найти условия вида `{% if request.url.path == view.url(request) %}` или `{% if request.url.path.startswith(...) %}` и применить тот же фильтр/функцию.

---

## Задача 3 — Проверить тест `test_sidebar_links.py`

Коммит `8358fc8` добавил `tests/test_sidebar_links.py`. Нужно убедиться, что тест:

1. Покрывает все типы nav-ссылок: model views, custom views, dropdown-ы с вложенными view.
2. Проверяет и en-admin (`/admin/...`), и ru-admin (`/ru/admin/...`).
3. Запускается и проходит после реализации задачи 1.

Если тест написан против старого (неисправленного) поведения — исправить его вместе с кодом.

**Команда для запуска:** `make test` или `uv run pytest tests/test_sidebar_links.py -v`

---

## Задача 4 — Проверить Home-ссылку (`/` в сайдбаре)

В starlette-admin "Home" — это не ModelView, а CustomView или встроенный роут. Убедиться, что он тоже проходит через `rebase_url`. В рендере из описания проблемы видно:

```html
<a class="nav-link" href="http://localhost:8000/admin/">  <!-- должно быть /ru/admin/ -->
```

Home-ссылка должна стать `http://localhost:8000/ru/admin/`.

---

## Задача 5 — Dropdown-ы с вложенными ссылками

В HTML из описания видно:

```html
<a href="http://localhost:8000/admin/role/list" class="dropdown-item">Roles</a>
<a href="http://localhost:8000/admin/user_with_roles/list" class="dropdown-item active fw-bold">User Roles</a>
```

Макрос `dropdown_link` тоже использует `view.url(request)` для каждого вложенного view. Убедиться, что фикс применён и к ним тоже, не только к верхнеуровневым пунктам.

---

## Порядок выполнения

1. Найти атрибут base_path у объекта admin (беглый `grep` или `print(dir(admin))` в коде).
2. Реализовать фильтр `rebase_url` в `__init__.py`.
3. Обновить `macros/views.html` — применить фильтр ко всем `view.url(request)` и к проверкам активного состояния.
4. Запустить `./demo.sh`, открыть `http://localhost:8000/ru/admin/`, проверить все ссылки в сайдбаре.
5. Запустить тесты, убедиться что `test_sidebar_links.py` проходит.
6. Проверить что en-admin (`http://localhost:8000/admin/`) по-прежнему работает корректно.

---

## На что обратить внимание

- `rebase_url` должен быть безопасен для внешних ссылок (Link-views с `url="https://..."`) — они не начинаются с base_path и должны оставаться нетронутыми.
- Если `_sa_base` и `base_url` совпадают (т.е. это дефолтная en-локаль), фильтр должен быть no-op.
- После изменений нужно убедиться, что JS в starlette-admin (датабл, AJAX-запросы) тоже использует правильные URL. Они обычно строятся из `data-` атрибутов, которые тоже генерируются через шаблоны — проверить отдельно.

---

по итогу нужно позаботится о тестах. текущий workflow сломан на (пред)последнем коммите (deluge)
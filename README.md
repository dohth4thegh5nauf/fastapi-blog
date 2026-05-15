# FastAPI Blog

> **Note:** This is a development fork. Original project: [pydanny/fastapi-blog](https://github.com/pydanny/fastapi-blog)

A simple, easy-to-use blog application built with FastAPI.

## 🚀 Quick Start

```bash
# Clone and install
git clone https://github.com/pydanny/fastapi-blog.git
cd fastapi-blog
make install

# Run demo
./demo.sh quickstart
```

Then open http://localhost:8000/admin (login: `admin` / `Admin123!`)

📚 **[See Full Quick Start Guide](QUICKSTART.md)** - includes all examples and detailed instructions

---

## Features

### Blog Features
- 📝 Write blog posts in Markdown with YAML frontmatter
- 🎨 Syntax highlighting for code blocks
- 📱 Responsive design
- 🌙 Dark mode
- 🎯 Overloadable templates
- 🔍 SEO-friendly with sitemap generation
- 🏷️ Tags and categories
- 📚 [Live examples](tests/examples/)

### Admin Panel Features
- ✨ Modern, beautiful admin UI (powered by starlette-admin)
- 👥 User management with role-based access control
- 📝 Visual post editor with Markdown support
- 🌍 Internationalization (English/Russian)
- 🔒 Secure authentication with bcrypt
- 📦 Custom fields (Markdown, Tags, Slugs)
- 🔍 Search, filtering, and pagination

### Developer Experience
- ⚡ Fast performance with FastAPI
- 🔒 Modern security practices
- 🧪 Comprehensive test coverage (50+ tests)
- 🚀 Python 3.12+ and 3.13 support
- 🐳 Docker support

## Architecture Overview

### Understanding the Three Types of Endpoints

FastAPI Blog provides three distinct systems:

#### 1. 📖 Public Blog (`/blog`)
- **Purpose**: Read-only public blog posts
- **Access**: Public (no authentication)
- **Documentation**: ✅ Visible in `/docs` (Swagger)
- **Type**: REST API endpoints

#### 2. 🎨 Admin Panel (`/admin`)
- **Purpose**: Web-based content management interface
- **Access**: Requires login (username/password)
- **Documentation**: ❌ Not in `/docs` — it's a UI, not an API!
- **Type**: HTML web application (powered by starlette-admin)
- **Use for**: Visual editing, user management, content creation

#### 3. 🔧 REST API (`/api/posts`)
- **Purpose**: Programmatic post management
- **Access**: Requires authentication
- **Documentation**: ✅ Visible in `/docs` **only if** `include_api=True`
- **Type**: REST API endpoints
- **Use for**: Scripts, automation, integrations

### Why isn't the Admin Panel in /docs?

The admin panel is a **web application** (like WordPress Admin or Django Admin), not a REST API. It uses HTML forms, sessions, and cookies for humans to interact with. Swagger/OpenAPI documents REST APIs, not web UIs.

**If you need programmatic access**, enable the REST API:

```python
fastapi_blog.add_blog_to_fastapi(
    app,
    include_api=True,  # ← This adds REST API to /docs
)
```

---

## Basic Usage

### Recommended: Unified Setup (One Function)

```python
from fastapi import FastAPI
import fastapi_blog

app = FastAPI()

# Single function configures everything
fastapi_blog.setup_fastapi_blog(
    app,
    posts_dirname="posts",
    include_api=False,  # Set True for REST API
    locales=["en", "ru"],  # Multiple languages
    default_locale="en",
    admin_username="admin",
    admin_password="change-me-in-production",
    secret_key="your-secret-key-here",
    enable_role_management=False,  # Set True for RBAC
)

@app.get("/")
async def index() -> dict:
    return {
        "message": "Visit /blog for posts, /admin for management",
        "blog": "http://localhost:8000/blog",
        "admin": "http://localhost:8000/admin",
    }
```

That's it! Now you have:
- 📝 Blog at `/blog`
- ⚙️ Admin panel at `/admin/en` and `/admin/ru`
- 🔒 Automatic database initialization
- 🌍 Multi-language admin panel

### Alternative: Separate Setup (More Control)

```python
from fastapi import FastAPI
import fastapi_blog

app = FastAPI()

# Add blog functionality
fastapi_blog.add_blog_to_fastapi(app, prefix="blog")

# Add admin panel
fastapi_blog.add_admin_to_app(app)

@app.get("/")
async def index() -> dict:
    return {
        "message": "Visit /blog for posts, /admin for management",
        "blog": "http://localhost:8000/blog",
        "admin": "http://localhost:8000/admin",
    }
```

That's it! Now you have:
- 📝 Blog at `/blog`
- ⚙️ Admin panel at `/admin`
- 🔒 Automatic database initialization

### Setup with REST API (for programmatic access)

```python
from fastapi import FastAPI
import fastapi_blog

app = FastAPI()

# Add blog with REST API enabled
fastapi_blog.add_blog_to_fastapi(
    app,
    prefix="blog",
    include_api=True,  # ← Enable REST API
    api_prefix="/api/posts",
    api_require_auth=True,
)

# Add admin panel for authentication
fastapi_blog.add_admin_to_app(app)
```

Now you have:
- 📝 Blog at `/blog`
- ⚙️ Admin panel at `/admin` (web UI)
- 🔧 REST API at `/api/posts/*` (visible in `/docs`)

### Basic Setup (Blog Only)

```python
from fastapi_blog import add_blog_to_fastapi
from fastapi import FastAPI

app = FastAPI()
app = add_blog_to_fastapi(app)
```

3. Add the first blog entry

Assuming your FastAPI app is defined in a `main.py` module at the root of your project, create a file at `posts/first-blog-post.md`:

```markdown
---
date: "2024-03-21T22:20:50.52Z"
published: true
tags:
  - fastapi
  - fastapi-blog
title: First blog post
description: This is the first blog post entry.
---

Exciting times in the world of fastapi-blog are ahead!

## This is a markdown header

And this is a markdown paragraph with a [link](https://github.com/pydanny/fastapi-blog).
```

4. Add the first page

Assuming your FastAPI app is defined in a `main.py` module at the root of your project, create a file at `pages/about.md`:

```markdown
---
title: "About Me"
description: "A little bit of background about me"
author: "Daniel Roy Greenfeld"
---

## Intro about me

I'm probably best known as "[pydanny](https://www.google.com/search?q=pydanny)", one of the authors of Two Scoops of Django.

I love to hang out with my [wife](https://audrey.feldroy.com/), play with my [daughter](/tags/uma), do [Brazilian Jiu-Jitsu](https://academyofbrazilianjiujitsu.com/), write [books](/books), and read books.

- [Mastodon](https://fosstodon.org/@danielfeldroy)
- [LinkedIn](https://www.linkedin.com/in/danielfeldroy/)
- [Twitter](https://twitter.com/pydanny)

## About this site

This site is written in:

- Python
- FastAPI
- fastapi-blog
- Sakura minimal CSS framework
- Markdown
- Vanilla HTML
```


## Advanced Usage

fastapi_blog is configurable through the `add_blog_to_fastapi` function.

### Adding app-controlled static media

Change the main app to mount StaticFiles:

```python
from fastapi_blog import add_blog_to_fastapi
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles


app = FastAPI()
app = add_blog_to_fastapi(app)
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
async def index() -> dict:
    return {
        "message": "Check out the blog at the URL",
        "url": "http://localhost:8000/blog",
    }
```

### Replacing the default templates

This example is Django-like in that your local templates will overload the default ones.

```python
import fastapi_blog
import jinja2
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles


django_style_jinja2_loader = jinja2.ChoiceLoader(
    [
        jinja2.FileSystemLoader("templates"),
        jinja2.PackageLoader("fastapi_blog", "templates"),
    ]
)

app = FastAPI()
app = fastapi_blog.add_blog_to_fastapi(
    app, prefix=prefix, jinja2_loader=django_style_jinja2_loader
)
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
async def index() -> dict:
    return {
        "message": "Check out the blog at the URL",
        "url": f"http://localhost:8000/blog",
    }
```


### Changing the location of the blog url

Perhaps you want to have the blog at the root?

```python
import fastapi_blog
from fastapi import FastAPI


app = FastAPI()
app = fastapi_blog.add_blog_to_fastapi(
    app, prefix="change"
)


@app.get("/api")
async def index() -> dict:
    return {
        "message": "Check out the blog at the URL",
        "url": "http://localhost:8000/change",
    }
```

## Blog at root URL

This is for when your blog/CMS needs to be at the root of the project

```python
import fastapi_blog
from fastapi import FastAPI


app = FastAPI()


@app.get("/api")
async def index() -> dict:
    return {
        "message": "Check out the blog at the URL",
        "url": "http://localhost:8000",
    }

# Because the prefix is None, the call to add_blog_to_fastapi
# needs to happen after the other view functions are defined.
app = fastapi_blog.add_blog_to_fastapi(app, prefix=None)
```


## Add favorite articles to the homepage

```python
import fastapi_blog
from fastapi import FastAPI


favorite_post_ids = {
    "code-code-code",
    "thirty-minute-rule",
    "2023-11-three-years-at-kraken-tech",
}

app = FastAPI()
app = fastapi_blog.add_blog_to_fastapi(app, favorite_post_ids=favorite_post_ids)


@app.get("/")
async def index() -> dict:
    return {
        "message": "Check out the blog at the URL",
        "url": "http://localhost:8000/blog",
    }
```

### Add page not in the blog list of posts

In the `pages` directory of your blog, add markdown files with frontmatter. You can then find it by going to the URL with that name. For example, adding this `pages/about.md` to the default config would make this appear at http://localhost:8000/blog/about.

```markdown
---
title: "About Daniel Roy Greenfeld"
description: "A little bit of background about Daniel Roy Greenfeld"
author: "Daniel Roy Greenfeld"
---

I'm probably best known as "[pydanny](https://www.google.com/search?q=pydanny)", one of the authors of [Two Scoops of Django](/books/tech).
```


## Installation and Running Example Sites

### Option 1: Local Development Setup (Recommended)

**Requirements:** Python 3.12+ (tested with Python 3.13.7)

```bash
# Clone the repository
git clone https://github.com/pydanny/fastapi-blog.git
cd fastapi-blog

# Create and activate virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install the project in development mode (this handles uv installation automatically)
make install

# Run the example blog
make run
```

### Option 2: Install from PyPI

```bash
pip install fastapi-blog
# Then create your own FastAPI app using the examples in the documentation
```

### Option 3: Docker (Local Dockerfile)

Or into a Docker container using the local Dockerfile:

```bash
docker build -t fastapi-blog .
docker run -d -p 8000:8000 fastapi-blog
```

### Option 4: Docker (Prebuilt)

Or using a prebuilt Docker image from GitHub Container Registry:

```bash
docker run -d -p 8000:8000 ghcr.io/pydanny/fastapi-blog:latest
```

This is if you just want to run the application without building it yourself.

## Development

### Running Tests and Quality Checks

```bash
# Run all tests with coverage
make test

# Run linting and formatting checks
make lint

# Auto-fix linting issues
make format

# Run type checking
make mypy

# Run all quality checks
make all
```

### Project Structure

```
fastapi-blog/
├── src/fastapi_blog/          # Main package
│   ├── main.py               # Core FastAPI integration
│   ├── router.py             # Blog routes and views  
│   ├── helpers.py            # Utility functions
│   └── templates/            # Jinja2 templates
├── tests/                    # Test suite
│   └── examples/             # Example configurations
├── .github/workflows/        # CI/CD workflows
└── pyproject.toml           # Project configuration
```

## Releasing a new version

1. Update the version in `pyproject.toml` and `fastapi_blog/__init__.py`

2. Update changelog.md

3. Build the distribution locally:

```bash
rm -rf dist
pip install -U build
python -m build
```

4. Upload the distribution to PyPI:

```bash
pip install -U twine
python -m twine upload dist/*
```

5. Create a new release on GitHub and tag the release:

```bash
git commit -am "Release for vXYZ"
make tag
```

## Contributors

<!-- readme: contributors -start -->
<table>
<tr>
    <td align="center">
        <a href="https://github.com/pydanny">
            <img src="https://avatars.githubusercontent.com/u/62857?v=4" width="100;" alt="pydanny"/>
            <br />
            <sub><b>Daniel Roy Greenfeld</b></sub>
        </a>
    </td>
    <td align="center">
        <a href="https://github.com/audreyfeldroy">
            <img src="https://avatars.githubusercontent.com/u/74739?v=4" width="100;" alt="audreyfeldroy"/>
            <br />
            <sub><b>Audrey Roy Greenfeld</b></sub>
        </a>
    </td></tr>
</table>
<!-- readme: contributors -end -->

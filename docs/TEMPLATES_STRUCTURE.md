# Templates Structure

FastAPI Blog uses a strict and consistent template organization structure.

## Directory Layout

```
src/fastapi_blog/
├── templates/              # Public blog templates
│   ├── layouts/            # Layout templates (note the 's')
│   │   └── base.html       # Base layout for blog pages
│   ├── partials/           # Reusable components
│   │   └── _post_short.html  # Post preview component
│   ├── 404.html            # Error page
│   ├── index.html          # Blog homepage
│   ├── page.html           # Static page template
│   ├── post.html           # Single post template
│   ├── posts.html          # Post list template
│   ├── tag.html            # Single tag page
│   └── tags.html           # Tags list
│
└── admin/
    └── templates/          # Admin panel templates
        ├── layouts/        # Layout templates (note the 's')
        │   ├── layout.html        # Base admin layout
        │   └── custom_base.html   # Custom admin base
        ├── partials/       # Admin components (currently empty)
        ├── home.html       # Admin dashboard
        ├── login.html      # Admin login page
        ├── markdown_edit.html   # Markdown editor
        └── markdown_list.html   # Markdown list view
```

## Key Principles

### 1. Layouts vs Layout

**Rule:** Always use `layouts/` (plural) for layout directories.

**Correct:**
```jinja2
{% extends "layouts/base.html" %}
```

**Incorrect:**
```jinja2
{% extends "layout/base.html" %}  ❌ Wrong!
```

### 2. Partials for Components

**Rule:** Reusable components go in `partials/` directory.

**Naming convention:** Prefix with underscore for components (optional but recommended).

**Example:**
```
partials/
├── _post_short.html   # Post preview component
├── _sidebar.html      # Sidebar component
└── _header.html       # Header component
```

### 3. Template Inheritance

**Public blog templates:**
```jinja2
{# All blog pages extend base layout #}
{% extends "layouts/base.html" %}

{% block title %}My Page{% endblock %}

{% block content %}
  {# Include partial components #}
  {% include "partials/_post_short.html" %}
{% endblock %}
```

**Admin templates:**
```jinja2
{# Most admin pages extend custom_base #}
{% extends "layouts/custom_base.html" %}

{% block content %}
  {# Admin-specific content #}
{% endblock %}

{# custom_base.html extends layout.html #}
{# layouts/custom_base.html: #}
{% extends "layouts/layout.html" %}

{# layout.html extends starlette-admin base #}
{# layouts/layout.html: #}
{% extends "@starlette-admin/layout.html" %}
```

## File Naming Conventions

### Layouts

**Rule:** Simple descriptive names without underscores.

**Examples:**
```
layouts/
├── base.html         # Base layout
├── layout.html       # Admin layout
└── custom_base.html  # Custom admin layout
```

### Partials

**Rule:** Prefix with underscore (recommended).

**Examples:**
```
partials/
├── _post_short.html  # Post component
├── _sidebar.html     # Sidebar component
├── _navigation.html  # Navigation component
└── _footer.html      # Footer component
```

### Page Templates

**Rule:** Descriptive names matching their purpose.

**Examples:**
```
index.html      # Homepage
post.html       # Single post page
posts.html      # Post list page
page.html       # Static page
tag.html        # Single tag page
tags.html       # Tags list page
404.html        # Error page
```

## Template Examples

### Creating a New Layout

**File:** `src/fastapi_blog/templates/layouts/blog_layout.html`

```jinja2
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{% block title %}My Blog{% endblock %}</title>
  {% block extra_head %}{% endblock %}
</head>
<body>
  {% include "partials/_header.html" %}
  
  <main>
    {% block content %}{% endblock %}
  </main>
  
  {% include "partials/_footer.html" %}
  
  {% block extra_scripts %}{% endblock %}
</body>
</html>
```

### Creating a New Partial

**File:** `src/fastapi_blog/templates/partials/_post_card.html`

```jinja2
<article class="post-card">
  <h2><a href="{{ post.url }}">{{ post.title }}</a></h2>
  <p class="meta">
    <time datetime="{{ post.date }}">{{ post.date | date }}</time>
    {% if post.tags %}
      | Tags: 
      {% for tag in post.tags %}
        <a href="/blog/tag/{{ tag }}">{{ tag }}</a>
      {% endfor %}
    {% endif %}
  </p>
  <div class="excerpt">
    {{ post.description or post.content[:200] }}
  </div>
  <a href="{{ post.url }}" class="read-more">Read more →</a>
</article>
```

### Using in a Page Template

**File:** `src/fastapi_blog/templates/blog_posts.html`

```jinja2
{% extends "layouts/base.html" %}

{% block title %}Blog Posts{% endblock %}

{% block content %}
  <h1>All Posts</h1>
  
  <div class="posts-grid">
    {% for post in posts %}
      {% include "partials/_post_card.html" %}
    {% endfor %}
  </div>
  
  {% if not posts %}
    <p>No posts available.</p>
  {% endif %}
{% endblock %}
```

## Admin Template Structure

### Custom Admin Layout

**File:** `src/fastapi_blog/admin/templates/layouts/custom_base.html`

```jinja2
{% extends "layouts/layout.html" %}

{# Customize starlette-admin layout #}
{% block header %}
  {# Custom header #}
{% endblock %}

{% block sidebar %}
  {# Custom sidebar #}
{% endblock %}

{% block content %}
  {# Your content here #}
  {{ super() }}
{% endblock %}
```

### Admin Page

**File:** `src/fastapi_blog/admin/templates/custom_page.html`

```jinja2
{% extends "layouts/custom_base.html" %}

{% block title %}Custom Admin Page{% endblock %}

{% block content %}
  <div class="container">
    <h1>Custom Admin Page</h1>
    <p>Your custom admin content here.</p>
  </div>
{% endblock %}
```

## Migration Guide

### Migrating from Old Structure

If you have old templates using `layout/` (singular), update them:

**Old:**
```jinja2
{% extends "layout/base.html" %}  ❌
```

**New:**
```jinja2
{% extends "layouts/base.html" %}  ✅
```

### Automated Migration

```bash
# Find all templates with old paths
find src/fastapi_blog/templates -name "*.html" -exec grep -l "layout/base.html" {} \;

# Replace automatically (Linux/macOS)
find src/fastapi_blog/templates -name "*.html" -exec sed -i 's|layout/base\.html|layouts/base.html|g' {} \;

# Verify changes
grep -r "extends.*layouts/base.html" src/fastapi_blog/templates/
```

## Best Practices

### 1. Keep Layouts Minimal

Layouts should contain:
- HTML structure (doctype, html, head, body)
- Common meta tags
- CSS/JS includes
- Block definitions

**Don't include** business logic in layouts.

### 2. Make Partials Reusable

Partials should:
- Accept variables via template context
- Have no hardcoded values
- Be self-contained
- Have clear documentation

### 3. Use Consistent Naming

- `layouts/` - plural
- `partials/` - plural
- Layout files - no underscore
- Partial files - underscore prefix (recommended)

### 4. Document Template Variables

Add comments at the top of templates:

```jinja2
{#
  Post card partial
  
  Required variables:
  - post: Post object with title, url, date, tags, description
  
  Optional variables:
  - show_excerpt: bool (default: false)
#}

<article class="post-card">
  {# ... #}
</article>
```

## Troubleshooting

### Template Not Found Error

**Error:** `TemplateNotFound: layouts/base.html`

**Check:**
1. File exists: `ls src/fastapi_blog/templates/layouts/base.html`
2. Path is correct in template: `{% extends "layouts/base.html" %}`
3. Template loader is configured correctly

### Wrong Template Loaded

**Problem:** Changes to template not reflected.

**Solutions:**
1. Restart development server
2. Clear template cache
3. Check Jinja2 auto_reload setting

### Partial Not Rendering

**Problem:** `{% include "partials/_component.html" %}` not working.

**Check:**
1. File exists in correct location
2. Path is relative to templates root
3. No syntax errors in partial
4. Variables are passed correctly

## Related Documentation

- [Jinja2 Templates](https://jinja.palletsprojects.com/en/3.1.x/templates/) - Official Jinja2 docs
- [Starlette Templates](https://www.starlette.io/templates/) - Starlette template docs
- [README.md](../README.md) - Project overview

---

**Last Updated:** 2026-05-15  
**Version:** 0.8.1+

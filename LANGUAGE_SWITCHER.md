# Language Switcher in Blog

## Quick Start

To enable the language switcher in your blog, pass `locales` parameter:

```python
import fastapi_blog
from fastapi import FastAPI

app = FastAPI()
fastapi_blog.add_blog_to_fastapi(
    app,
    locales=["en", "ru"],  # Enable language switcher
    default_locale="en",
)
```

## What You Get

1. **Dropdown menu** in blog header with language options (English/Русский)
2. **URL-based localization**: `/blog/en/posts`, `/blog/ru/posts`
3. **Auto-redirect** when switching languages
4. **Preserves current page** when switching
5. **Hidden automatically** when only one locale is configured

## URL Structure

With locales enabled:
- `/blog/en/` - English homepage
- `/blog/en/posts` - English articles
- `/blog/ru/` - Russian homepage  
- `/blog/ru/posts` - Russian articles

Legacy URLs still work (use Accept-Language header):
- `/blog/` - Auto-detected language
- `/blog/posts` - Auto-detected language

## Examples

See working examples in:
- `tests/examples/quickstart.py` - Full setup with admin
- `tests/examples/admin_i18n.py` - I18n focus
- `tests/examples/defaults.py` - Minimal setup

## How It Works

1. **URL takes priority**: `/blog/ru/posts` always shows Russian
2. **Fallback to Accept-Language**: `/blog/posts` uses browser language
3. **Default locale**: Used when no match found

## Testing

Run the quickstart example:
```bash
cd tests/examples
uvicorn quickstart:app --reload
```

Then visit:
- http://localhost:8000/blog/en/ (English)
- http://localhost:8000/blog/ru/ (Russian)

Click the language switcher to see the redirect in action!

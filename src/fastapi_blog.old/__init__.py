from typing import Any

import jinja2
from fastapi import FastAPI
from fastapi.templating import Jinja2Templates

from .admin import add_admin_to_app
from .editor import add_editor_to_app, get_api_router
from .main import add_blog_to_fastapi
from .router import get_blog_router


__version__ = "0.8.0"

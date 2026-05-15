import pathlib
import warnings
from typing import Any

import jinja2
import yaml
from fastapi import APIRouter, Depends, FastAPI, HTTPException, Path, Request, status
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from . import helpers
from .models import (
    SLUG_PATTERN,
    LoosePostPayload,
    StrictPostPayload,
    is_valid_slug,
    payload_model,
)


async def require_authentication(request: Request) -> dict:
    """Require authentication via session cookie.

    This function is part of fastapi-blog and only checks session-based
    authentication (starlette-admin SessionMiddleware).

    For JWT authentication, the parent application should override this
    dependency or add custom middleware.

    Returns:
        dict with user info if authenticated

    Raises:
        HTTPException 401 if not authenticated

    """
    # Check session cookie (set by starlette-admin or SessionMiddleware)
    # Only check session if SessionMiddleware is installed
    if "session" in request.scope:
        user = request.session.get("user")
        if user:
            return {"username": user, "is_admin": request.session.get("is_admin", False)}

    # No valid session found
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required. Please login via admin panel.",
        headers={"WWW-Authenticate": "Session"},
    )


async def optional_authentication(request: Request) -> dict | None:
    """Return user info if authenticated, None otherwise.

    This is used when require_auth=False (e.g., in tests).
    Does NOT raise 401, just returns None.

    Returns:
        dict with user info if authenticated, None otherwise

    """
    # Check if session exists (SessionMiddleware installed)
    if "session" not in request.scope:
        return None
    user = request.session.get("user")
    if user:
        return {"username": user, "is_admin": request.session.get("is_admin", False)}
    return None


def _post_path(slug: str, posts_dirname: str) -> pathlib.Path:
    if not is_valid_slug(slug):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Invalid slug. Allowed: lowercase letters, digits, hyphens (max 100)."
            ),
        )
    return pathlib.Path(posts_dirname) / f"{slug}.md"


def _serialize(payload: StrictPostPayload | LoosePostPayload) -> str:
    fm_dump = payload.frontmatter.model_dump(exclude_none=True)
    fm_yaml = yaml.safe_dump(fm_dump, sort_keys=False, allow_unicode=True)
    return f"---\n{fm_yaml}---\n\n{payload.content.rstrip()}\n"


def _parse_file(path: pathlib.Path) -> dict[str, Any]:
    raw = path.read_text()
    parts = raw.split("---")
    if len(parts) < 3:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Post file is malformed: {path.name}",
        )
    try:
        frontmatter = yaml.safe_load(parts[1]) or {}
    except yaml.YAMLError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Invalid YAML in {path.name}: {exc}",
        ) from exc
    content = "---".join(parts[2:]).lstrip("\n")
    return {"frontmatter": frontmatter, "content": content}


def get_api_router(
    posts_dirname: str = "posts",
    strict: bool = True,
    require_auth: bool = True,
    admin_username: str | None = None,
    admin_password: str | None = None,
) -> APIRouter:
    """Get REST API router for post management.

    This function returns a configured APIRouter that can be included in any
    FastAPI application. It provides REST API endpoints for CRUD operations
    on markdown posts.

    Args:
        posts_dirname: Directory containing markdown posts (default: 'posts')
        strict: Use strict frontmatter validation (default: True)
        require_auth: Require authentication for all endpoints (default: True)
        admin_username: Admin username for unified auth (optional)
        admin_password: Admin password for unified auth (optional)

    Returns:
        APIRouter with REST API endpoints

    Example:
        ```python
        from fastapi import (
            FastAPI,
        )
        from fastapi_blog.editor import (
            get_api_router,
        )

        app = FastAPI()
        api_router = get_api_router(
            require_auth=True
        )
        app.include_router(
            api_router,
            prefix="/api/posts",
        )
        ```

    """
    api_router = APIRouter(tags=["editor"])
    Payload = payload_model(strict)
    slug_path = Path(pattern=SLUG_PATTERN, max_length=100)

    # Setup authentication dependency
    if require_auth:
        if admin_username and admin_password:
            # Use unified auth (session + Basic auth)
            from .auth import require_current_user

            async def auth_func(request: Request) -> dict:
                username = await require_current_user(
                    request,
                    admin_username=admin_username,
                    admin_password=admin_password,
                )
                return {"username": username}
        else:
            # Use legacy session-only auth
            auth_func = require_authentication
    else:
        auth_func = optional_authentication

    @api_router.get("/{slug}/raw")
    async def get_raw(
        slug: str = slug_path,
        user: dict | None = Depends(auth_func),
    ) -> dict[str, Any]:
        path = _post_path(slug, posts_dirname)
        if not path.is_file():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Post '{slug}' not found",
            )
        data = _parse_file(path)
        return {"slug": slug, **data}

    @api_router.post("/create/{slug}", status_code=status.HTTP_201_CREATED)
    async def create_post(
        payload: Payload,  # type: ignore[valid-type]
        slug: str = slug_path,
        user: dict | None = Depends(auth_func),
    ) -> dict[str, str]:
        path = _post_path(slug, posts_dirname)
        if path.exists():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Post '{slug}' already exists",
            )
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_serialize(payload))
        helpers.list_posts.cache_clear()
        return {"slug": slug, "status": "created"}

    @api_router.put("/update/{slug}")
    async def update_post(
        payload: Payload,  # type: ignore[valid-type]
        slug: str = slug_path,
        user: dict | None = Depends(auth_func),
    ) -> dict[str, str]:
        path = _post_path(slug, posts_dirname)
        if not path.is_file():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Post '{slug}' not found",
            )
        path.write_text(_serialize(payload))
        helpers.list_posts.cache_clear()
        return {"slug": slug, "status": "updated"}

    @api_router.delete("/delete/{slug}", status_code=status.HTTP_204_NO_CONTENT)
    async def delete_post(
        slug: str = slug_path,
        user: dict | None = Depends(auth_func),
    ) -> None:
        path = _post_path(slug, posts_dirname)
        if not path.is_file():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Post '{slug}' not found",
            )
        path.unlink()
        helpers.list_posts.cache_clear()

    @api_router.post("/save")
    async def save_post(
        request: Request,
        user: dict | None = Depends(auth_func),
    ) -> JSONResponse:
        data = await request.json()
        slug = data.get("slug")
        if not slug:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Slug is required",
            )

        frontmatter = data.get("frontmatter", {})
        content = data.get("content", "")

        try:
            payload = Payload(  # type: ignore[call-arg]
                frontmatter=frontmatter, content=content
            )
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid payload: {str(e)}",
            ) from e

        path = _post_path(slug, posts_dirname)
        is_new = not path.exists()

        if is_new:
            path.parent.mkdir(parents=True, exist_ok=True)

        path.write_text(_serialize(payload))
        helpers.list_posts.cache_clear()

        return JSONResponse(
            content={"slug": slug, "status": "created" if is_new else "updated"},
            status_code=status.HTTP_201_CREATED if is_new else status.HTTP_200_OK,
        )

    return api_router


def add_editor_to_app(
    app: FastAPI,
    prefix: str = "/api/posts",
    posts_dirname: str = "posts",
    strict: bool = True,
    ui: bool = True,
    ui_prefix: str = "/admin/editor",
    require_auth: bool = True,
) -> FastAPI:
    """Add editor REST API and optional UI to FastAPI app.

    .. deprecated:: 0.8.0
        The UI parameter (ui=True) is deprecated. Use add_admin_to_app() for
        admin interface instead. The REST API will remain available but should
        be enabled explicitly via include_api parameter in future versions.

    Args:
        app: FastAPI application instance
        prefix: URL prefix for REST API (default: '/api/posts')
        posts_dirname: Directory containing markdown posts (default: 'posts')
        strict: Use strict frontmatter validation (default: True)
        ui: (DEPRECATED) Include UI routes (default: True)
        ui_prefix: (DEPRECATED) URL prefix for UI (default: '/admin/editor')
        require_auth: Require authentication for all endpoints (default: True)

    Returns:
        FastAPI application with editor routes added

    Example:
        ```python
        from fastapi import (
            FastAPI,
        )
        from fastapi_blog import (
            add_editor_to_app,
        )

        app = FastAPI()
        # REST API only (recommended)
        add_editor_to_app(
            app, ui=False
        )

        # Or use new admin panel instead
        from fastapi_blog.admin import (
            add_admin_to_app,
        )

        add_admin_to_app(
            app
        )
        ```

    """
    # Emit deprecation warning if UI is enabled
    if ui:
        warnings.warn(
            "The 'ui' parameter in add_editor_to_app() is deprecated and will be "
            "removed in version 1.0.0. Please use add_admin_to_app() from "
            "fastapi_blog.admin for a modern admin interface with better features. "
            "The REST API (/api/posts) will remain available.",
            DeprecationWarning,
            stacklevel=2,
        )

    # Use get_api_router() to get REST API endpoints
    api_router = get_api_router(
        posts_dirname=posts_dirname,
        strict=strict,
        require_auth=require_auth,
    )
    app.include_router(api_router, prefix=prefix)

    # Add deprecated UI routes if requested
    if ui:
        _add_ui_routes(
            app,
            ui_prefix=ui_prefix,
            posts_dirname=posts_dirname,
            strict=strict,
            require_auth=require_auth,
        )

    return app


def _add_ui_routes(
    app: FastAPI,
    ui_prefix: str,
    posts_dirname: str,
    strict: bool,
    require_auth: bool,
) -> None:
    """Add deprecated UI routes for editor."""
    ui_router = APIRouter(prefix=ui_prefix, tags=["editor-ui"])
    slug_path = Path(pattern=SLUG_PATTERN, max_length=100)
    auth_func = require_authentication if require_auth else optional_authentication

    # Prep templates
    env = jinja2.Environment(
        loader=jinja2.PackageLoader("fastapi_blog", "templates"),
        autoescape=jinja2.select_autoescape(["html", "xml"]),
    )
    templates = Jinja2Templates(env=env)

    def _context(request: Request, **kwargs: Any) -> dict[str, Any]:
        return {"request": request, **kwargs}

    @ui_router.get("/", response_class=HTMLResponse)
    async def editor_index(
        request: Request,
        user: dict | None = Depends(auth_func),
    ) -> Any:
        posts = helpers.list_posts(
            posts_dirname=posts_dirname, strict=strict, published=True
        )
        drafts = helpers.list_posts(
            posts_dirname=posts_dirname, strict=strict, published=False
        )
        return templates.TemplateResponse(
            request=request,
            name="admin/list.html",
            context=_context(request, posts=list(posts) + list(drafts)),
        )

    @ui_router.get("/new", response_class=HTMLResponse)
    async def editor_new(
        request: Request,
        user: dict | None = Depends(auth_func),
    ) -> Any:
        return templates.TemplateResponse(
            request=request,
            name="admin/edit.html",
            context=_context(
                request,
                is_new=True,
                slug="",
                frontmatter={"title": "", "date": "", "tags": [], "published": False},
                content="",
            ),
        )

    @ui_router.get("/{slug}", response_class=HTMLResponse)
    async def editor_edit(
        request: Request,
        slug: str = slug_path,
        user: dict | None = Depends(auth_func),
    ) -> Any:
        path = _post_path(slug, posts_dirname)
        if not path.is_file():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Post '{slug}' not found",
            )
        data = _parse_file(path)
        return templates.TemplateResponse(
            request=request,
            name="admin/edit.html",
            context=_context(
                request,
                is_new=False,
                slug=slug,
                frontmatter=data["frontmatter"],
                content=data["content"],
            ),
        )

    app.include_router(ui_router)

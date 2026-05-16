import os

import jinja2
from fastapi import FastAPI
from fastapi.templating import Jinja2Templates

from .router import get_blog_router


def add_blog_to_fastapi(
    app: FastAPI,
    prefix: str | None = "blog",
    jinja2_loader: jinja2.BaseLoader = jinja2.PackageLoader(
        "fastapi_blog", "templates"
    ),
    jinja2_extensions: set[str] = {
        "jinja2_time.TimeExtension",
        "jinja2.ext.debug",
    },
    favorite_post_ids: set[str] = set(),
    mount_statics: bool = True,
    strict_frontmatter: bool = True,
    sanitize_html: bool = True,
    posts_dirname: str = "posts",
    pages_dirname: str = "pages",
    include_api: bool | None = None,
    api_prefix: str = "/api/posts",
    api_require_auth: bool = True,
    locales: list[str] = ["en"],
    default_locale: str = "en",
    admin_username: str | None = None,
    admin_password: str | None = None,
) -> FastAPI:
    """Add blog to FastAPI application.

    Args:
        app: FastAPI application instance
        prefix: URL prefix for blog routes (default: 'blog', None for root)
        jinja2_loader: Jinja2 template loader
        jinja2_extensions: Set of Jinja2 extensions to enable
        favorite_post_ids: Set of post slugs to feature on homepage
        mount_statics: Whether to mount static files (deprecated)
        strict_frontmatter: Use strict frontmatter validation
        sanitize_html: Sanitize HTML in markdown content
        posts_dirname: Directory containing blog posts
        pages_dirname: Directory containing pages
        include_api: Include REST API for post management.
                     Default: from FASTAPI_BLOG_INCLUDE_API env var, or False.
                     When True, adds REST endpoints visible in /docs.
                     Note: Admin panel (/admin) is separate - it's a web UI, not REST API.
        api_prefix: URL prefix for REST API (default: '/api/posts')
        api_require_auth: Require authentication for API (default: True)
        locales: List of supported locales for blog UI (default: ['en'])
        default_locale: Default locale when Accept-Language not matched (default: 'en')
        admin_username: Admin username for REST API auth (optional)
        admin_password: Admin password for REST API auth (optional)

    Returns:
        FastAPI application with blog routes added

    Example:
        ```python
        from fastapi import (
            FastAPI,
        )
        from fastapi_blog import (
            add_blog_to_fastapi,
        )

        app = FastAPI()

        # Basic blog
        add_blog_to_fastapi(
            app
        )

        # With REST API enabled
        add_blog_to_fastapi(
            app,
            include_api=True,
        )
        ```

    """
    # Handle environment variable for include_api
    if include_api is None:
        env_value = os.getenv("FASTAPI_BLOG_INCLUDE_API", "false").lower()
        include_api = env_value in ("true", "1", "yes")

    # Prep the templates
    env = jinja2.Environment(
        loader=jinja2_loader,
        extensions=list(jinja2_extensions),
        autoescape=jinja2.select_autoescape(["html", "xml"]),
    )
    templates = Jinja2Templates(env=env)

    # Add redirects
    from starlette.responses import RedirectResponse

    # Only add root redirect when prefix is set
    # When prefix=None, the blog router itself handles /
    if prefix is not None:

        @app.get("/", include_in_schema=False)
        async def root_redirect():
            return RedirectResponse(url=f"/{prefix}/", status_code=302)

        # Add redirect from /{prefix} to /{prefix}/
        @app.get(f"/{prefix}", include_in_schema=False)
        async def blog_prefix_redirect():
            return RedirectResponse(url=f"/{prefix}/", status_code=302)

    # Router controls:
    # 1. Main router without locale prefix (uses default_locale)
    # 2. Routers for non-default locales with /{locale} prefix
    # 3. Redirect from /{default_locale} to clean URLs

    # Create main router for default locale (no locale in URL)
    main_router = get_blog_router(
        templates=templates,
        favorite_post_ids=favorite_post_ids,
        strict=strict_frontmatter,
        sanitize_html=sanitize_html,
        posts_dirname=posts_dirname,
        pages_dirname=pages_dirname,
        locales=locales,
        default_locale=default_locale,
        locale=default_locale,
    )

    # Mount main router without locale prefix
    if prefix is not None:
        app.include_router(main_router, prefix=f"/{prefix}", tags=["blog"])
    else:
        app.include_router(main_router, tags=["blog"])

    # Create routers for non-default locales
    for locale in locales:
        if locale == default_locale:
            continue  # Skip default locale - it's already mounted

        router = get_blog_router(
            templates=templates,
            favorite_post_ids=favorite_post_ids,
            strict=strict_frontmatter,
            sanitize_html=sanitize_html,
            posts_dirname=posts_dirname,
            pages_dirname=pages_dirname,
            locales=locales,
            default_locale=default_locale,
            locale=locale,
        )

        # Mount with locale prefix
        if prefix is not None:
            app.include_router(router, prefix=f"/{locale}/{prefix}", tags=["blog"])
        else:
            app.include_router(router, prefix=f"/{locale}", tags=["blog"])

    # Add middleware to redirect URLs with default locale to clean URLs
    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.requests import Request as StarletteRequest

    class DefaultLocaleRedirectMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request: StarletteRequest, call_next):
            path = request.url.path

            # Check if path starts with /{default_locale}
            if prefix is not None:
                # Check for /{default_locale}/blog/...
                locale_prefix = f"/{default_locale}/{prefix}"
                if path.startswith(locale_prefix):
                    # Redirect to /blog/...
                    new_path = path[len(f"/{default_locale}") :]
                    # Preserve query string if present
                    if request.url.query:
                        new_path = f"{new_path}?{request.url.query}"
                    return RedirectResponse(url=new_path, status_code=302)
            else:
                # Check for /{default_locale}/...
                locale_prefix = f"/{default_locale}/"
                if path.startswith(locale_prefix):
                    # Redirect to /...
                    new_path = path[len(f"/{default_locale}") :]
                    # Preserve query string if present
                    if request.url.query:
                        new_path = f"{new_path}?{request.url.query}"
                    return RedirectResponse(url=new_path, status_code=302)

            return await call_next(request)

    app.add_middleware(DefaultLocaleRedirectMiddleware)

    # Optionally include REST API for post management
    if include_api:
        from .editor import get_api_router

        api_router = get_api_router(
            posts_dirname=posts_dirname,
            strict=strict_frontmatter,
            require_auth=api_require_auth,
            admin_username=admin_username,
            admin_password=admin_password,
        )
        app.include_router(api_router, prefix=api_prefix, tags=["api"])

    return app

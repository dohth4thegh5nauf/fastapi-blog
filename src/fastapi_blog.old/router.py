import collections
import pathlib
from typing import Any

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from . import helpers


def get_blog_router(
    templates: Jinja2Templates,
    favorite_post_ids: set[str] = set(),
    strict: bool = True,
    sanitize_html: bool = True,
    posts_dirname: str = "posts",
    pages_dirname: str = "pages",
) -> APIRouter:
    router = APIRouter()

    def _list_posts() -> tuple[dict, ...]:
        return helpers.list_posts(posts_dirname=posts_dirname, strict=strict)

    @router.get("/")
    async def blog_index(request: Request, response_class=HTMLResponse):
        posts = _list_posts()
        recent_3 = posts[:3]

        favorite_posts: list[dict[Any, Any]] = list(
            filter(lambda x: x["slug"] in favorite_post_ids, posts)
        )

        return templates.TemplateResponse(
            request=request,
            name="index.html",
            context={"recent_3": recent_3, "favorite_posts": favorite_posts},
        )

    @router.get("/posts/{post_id}")
    async def blog_post(post_id: str, request: Request, response_class=HTMLResponse):
        matches = [x for x in _list_posts() if x["slug"] == post_id]
        if not matches:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Post '{post_id}' not found",
            )
        post = dict(matches[0])
        content = (
            pathlib.Path(f"{posts_dirname}/{post_id}.md").read_text().split("---")[2]
        )
        post["content"] = helpers.markdown(content, sanitize=sanitize_html)

        return templates.TemplateResponse(
            request=request, name="post.html", context={"post": post}
        )

    @router.get("/posts")
    async def blog_posts(request: Request, response_class=HTMLResponse):
        posts = _list_posts()

        return templates.TemplateResponse(
            request=request, name="posts.html", context={"posts": posts}
        )

    @router.get("/tags")
    async def blog_tags(request: Request, response_class=HTMLResponse):
        posts = _list_posts()

        unsorted_tags: dict = {}
        for post in posts:
            page_tags = post.get("tags", []) or []
            for tag in page_tags:
                if tag in unsorted_tags:
                    unsorted_tags[tag] += 1
                else:
                    unsorted_tags[tag] = 1

        # Sort by value (number of articles per tag)
        tags: dict = collections.OrderedDict(
            sorted(unsorted_tags.items(), key=lambda x: x[1], reverse=True)
        )

        return templates.TemplateResponse(
            request=request, name="tags.html", context={"tags": tags}
        )

    @router.get("/tags/{tag_id}")
    async def blog_tag(tag_id: str, request: Request, response_class=HTMLResponse):
        posts = [x for x in _list_posts() if tag_id in (x.get("tags") or [])]

        return templates.TemplateResponse(
            request=request, name="tag.html", context={"tag_id": tag_id, "posts": posts}
        )

    @router.get("/{page_id}")
    async def blog_page(page_id: str, request: Request, response_class=HTMLResponse):
        path = pathlib.Path(f"{pages_dirname}/{page_id}.md")
        try:
            page: dict[str, str | dict] = helpers.load_content_from_markdown_file(
                path, sanitize=sanitize_html
            )
        except FileNotFoundError:
            return templates.TemplateResponse(
                request=request, name="404.html", status_code=404
            )
        page["slug"] = page_id

        return templates.TemplateResponse(
            request=request, name="page.html", context={"page": page}
        )

    return router

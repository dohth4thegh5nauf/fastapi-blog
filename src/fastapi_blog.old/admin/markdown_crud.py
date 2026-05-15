"""CRUD operations for markdown files using starlette-admin CustomView."""

import os
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml
from starlette.requests import Request
from starlette.responses import Response
from starlette.templating import Jinja2Templates
from starlette_admin.views import CustomView


# Simple identity function - labels will be set dynamically per locale
def _(message: str) -> str:
    """Identity function. Labels are set dynamically in _create_admin_for_locale()."""
    return message


def get_posts_directory() -> str:
    """Get posts directory from environment or default location.

    Returns:
      Path to posts directory as string

    """
    posts_dir_env = os.getenv("POSTS_DIR")
    if posts_dir_env:
        return posts_dir_env

    # Try to find posts directory relative to the app
    backend_dir = (
        Path.cwd() / "backend" if (Path.cwd() / "backend").exists() else Path.cwd()
    )
    return str(backend_dir / "posts")


class MarkdownPost:
    """Represents a markdown post with frontmatter."""

    def __init__(self, slug: str, frontmatter: dict[str, Any], content: str):
        """Initialize markdown post with slug, frontmatter, and content."""
        self.slug = slug
        self.frontmatter = frontmatter
        self.content = content
        self.title = frontmatter.get("title", slug)
        self.date = frontmatter.get("date", "")
        self.published = frontmatter.get("published", False)
        self.tags = frontmatter.get("tags", [])


class MarkdownFileManager:
    """Manager for reading/writing markdown files."""

    def __init__(self, posts_dir: str = "posts"):
        """Initialize file manager with posts directory."""
        self.posts_dir = Path(posts_dir)
        self.posts_dir.mkdir(exist_ok=True)

    def list_posts(self) -> list[MarkdownPost]:
        """List all markdown posts."""
        posts = []
        for file_path in self.posts_dir.glob("*.md"):
            try:
                post = self.load_post(file_path.stem)
                if post:
                    posts.append(post)
            except Exception as e:
                print(f"Error loading {file_path}: {e}")

        # Sort by date descending (handle both datetime and string)
        def get_sort_key(p):
            if not p.date:
                return ""
            # Convert datetime to string for consistent comparison
            if isinstance(p.date, datetime):
                return p.date.isoformat()
            return str(p.date)

        posts.sort(key=get_sort_key, reverse=True)
        return posts

    def load_post(self, slug: str) -> MarkdownPost | None:
        """Load a single post by slug."""
        file_path = self.posts_dir / f"{slug}.md"
        if not file_path.exists():
            return None

        content = file_path.read_text(encoding="utf-8")

        # Parse frontmatter
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                frontmatter_text = parts[1]
                body = parts[2].strip()
                try:
                    frontmatter = yaml.safe_load(frontmatter_text) or {}
                except Exception as e:
                    print(f"Error parsing frontmatter for {slug}: {e}")
                    frontmatter = {}
            else:
                frontmatter = {}
                body = content
        else:
            frontmatter = {}
            body = content

        return MarkdownPost(slug, frontmatter, body)

    def save_post(self, slug: str, frontmatter: dict[str, Any], content: str) -> None:
        """Save a post to file."""
        # Construct markdown with frontmatter
        frontmatter_yaml = yaml.dump(frontmatter, allow_unicode=True, sort_keys=False)
        markdown = f"---\n{frontmatter_yaml}---\n\n{content}"

        file_path = self.posts_dir / f"{slug}.md"
        file_path.write_text(markdown, encoding="utf-8")

    def delete_post(self, slug: str) -> bool:
        """Delete a post."""
        file_path = self.posts_dir / f"{slug}.md"
        if file_path.exists():
            file_path.unlink()
            return True
        return False


class MarkdownListView(CustomView):
    """List view for markdown posts."""

    def __init__(self, posts_dir: str = "posts"):
        """Initialize list view with posts directory."""
        super().__init__(
            label=_("Posts"),
            icon="fa fa-file-text",
            path="/posts/list",
            template_path="markdown_list.html",
            name="posts:list",
        )
        self.manager = MarkdownFileManager(posts_dir)

    async def render(self, request: Request, templates: Jinja2Templates) -> Response:
        """Render list of posts."""
        posts = self.manager.list_posts()

        # Convert to dict for template
        posts_data = [
            {
                "slug": p.slug,
                "title": p.title,
                "date": self._format_date(p.date),
                "published": p.published,
                "tags": ", ".join(p.tags)
                if isinstance(p.tags, list)
                else str(p.tags)
                if p.tags
                else "",
            }
            for p in posts
        ]

        # Get current locale for translations
        from starlette_admin.i18n import get_locale

        locale = get_locale()

        # Translations dictionary
        translations = {
            "ru": {
                "posts": "Посты",
                "admin": "Админ",
                "new_post": "Новый пост",
                "title": "Заголовок",
                "slug": "URL",
                "date": "Дата",
                "status": "Статус",
                "tags": "Теги",
                "actions": "Действия",
                "published": "Опубликовано",
                "draft": "Черновик",
                "edit": "Редактировать",
                "delete": "Удалить",
                "no_posts_found": "Посты не найдены.",
                "create_first_post": "Создайте свой первый пост",
                "delete_confirm": "Удалить пост",
                "error": "Ошибка",
                "failed_to_delete": "Не удалось удалить",
            },
            "en": {
                "posts": "Posts",
                "admin": "Admin",
                "new_post": "New Post",
                "title": "Title",
                "slug": "Slug",
                "date": "Date",
                "status": "Status",
                "tags": "Tags",
                "actions": "Actions",
                "published": "Published",
                "draft": "Draft",
                "edit": "Edit",
                "delete": "Delete",
                "no_posts_found": "No posts found.",
                "create_first_post": "Create your first post",
                "delete_confirm": "Delete post",
                "error": "Error",
                "failed_to_delete": "Failed to delete",
            },
        }

        # Get translations for current locale (default to English)
        t = translations.get(locale, translations["en"])

        return templates.TemplateResponse(
            request=request,
            name=self.template_path,
            context={
                "title": self.title(request),
                "posts": posts_data,
                "base_url": request.scope["root_path"],
                "t": t,  # Add translations
            },
        )

    def _format_date(self, date_value) -> str:
        """Format date for display."""
        if not date_value:
            return ""
        if isinstance(date_value, datetime):
            return date_value.strftime("%Y-%m-%d")
        return str(date_value)


class MarkdownEditView(CustomView):
    """Edit view for markdown posts."""

    def __init__(self, posts_dir: str = "posts"):
        """Initialize edit view with posts directory."""
        super().__init__(
            label=_("Edit Post"),
            path="/posts/edit/{slug}",
            template_path="markdown_edit.html",
            name="posts:edit",
            add_to_menu=False,  # Don't show in menu
        )
        self.manager = MarkdownFileManager(posts_dir)

    async def render(self, request: Request, templates: Jinja2Templates) -> Response:
        """Render edit form."""
        slug = request.path_params.get("slug")
        if not slug:
            return templates.TemplateResponse(
                request=request,
                name="error.html",
                context={"error": "Missing slug parameter"},
                status_code=400,
            )
        post = self.manager.load_post(slug)

        if not post:
            return templates.TemplateResponse(
                request=request,
                name="admin/404.html",
                context={
                    "title": "Post not found",
                    "message": f'Post "{slug}" not found',
                },
                status_code=404,
            )

        return templates.TemplateResponse(
            request=request,
            name=self.template_path,
            context={
                "title": f"Edit: {post.title}",
                "post": {
                    "slug": post.slug,
                    "title": post.title,
                    "content": post.content,
                    "frontmatter": post.frontmatter,
                },
                "base_url": request.scope["root_path"],
            },
        )


class MarkdownCreateView(CustomView):
    """Create view for new markdown posts."""

    def __init__(self, posts_dir: str = "posts"):
        """Initialize create view with posts directory."""
        super().__init__(
            label=_("New Post"),
            path="/posts/new",
            template_path="markdown_edit.html",
            name="posts:new",
            add_to_menu=False,
        )
        self.manager = MarkdownFileManager(posts_dir)

    async def render(self, request: Request, templates: Jinja2Templates) -> Response:
        """Render create form."""
        return templates.TemplateResponse(
            request=request,
            name=self.template_path,
            context={
                "title": "Create New Post",
                "post": {
                    "slug": "",
                    "title": "",
                    "content": "",
                    "frontmatter": {
                        "published": False,
                        "tags": [],
                        "date": datetime.now().strftime("%Y-%m-%d"),
                    },
                },
                "is_new": True,
                "base_url": request.scope["root_path"],
            },
        )

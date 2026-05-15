"""Custom fields for starlette-admin.

Provides enhanced field types for markdown content and tags.
"""

from typing import Any

from starlette.datastructures import FormData
from starlette.requests import Request
from starlette_admin._types import RequestAction
from starlette_admin.fields import BaseField, TextAreaField


class MarkdownField(TextAreaField):
    """Enhanced textarea field for markdown content.

    Provides a larger text area optimized for markdown editing.
    Future enhancements may include:
    - Live preview
    - Syntax highlighting
    - Integration with markdown editors (SimpleMDE, EasyMDE)
    """

    def __init__(
        self,
        name: str,
        label: str | None = None,
        rows: int = 20,
        **kwargs: Any,
    ):
        """Initialize markdown field.

        Args:
            name: Field name
            label: Field label (defaults to name)
            rows: Number of rows for textarea (default: 20)
            **kwargs: Additional field options

        """
        super().__init__(name, label=label, **kwargs)
        self.rows = rows

    async def serialize_value(
        self, request: Request, value: Any, action: RequestAction
    ) -> Any:
        """Serialize markdown content for display.

        Args:
            request: Starlette request
            value: Field value
            action: Current action (list, detail, edit, create)

        Returns:
            Serialized value

        """
        if not value:
            return value

        if action == "list":
            # Show truncated preview in list view
            preview = str(value)[:100]
            if len(str(value)) > 100:
                preview += "..."
            return preview
        elif action == "detail":
            # Render markdown to HTML in detail view
            import markdown
            from markupsafe import Markup

            return Markup(markdown.markdown(Markup.escape(value)))
        return value


class TagsField(BaseField):
    """Field for managing comma-separated tags.

    Handles conversion between string and list representations.
    Displays tags as badges in list view.
    """

    def __init__(
        self,
        name: str,
        label: str | None = None,
        placeholder: str = "tag1, tag2, tag3",
        **kwargs: Any,
    ):
        """Initialize tags field.

        Args:
            name: Field name
            label: Field label (defaults to name)
            placeholder: Placeholder text
            **kwargs: Additional field options

        """
        super().__init__(name, label=label, **kwargs)
        self.placeholder = placeholder

    async def parse_form_data(
        self, request: Request, form_data: FormData, action: RequestAction
    ) -> Any:
        """Parse tags from form data.

        Args:
            request: Starlette request
            form_data: Form data
            action: Request action

        Returns:
            List of tags

        """
        value = form_data.get(self.name)
        if isinstance(value, str):
            # Split by comma and strip whitespace
            return [tag.strip() for tag in value.split(",") if tag.strip()]
        return value or []

    async def serialize_value(
        self, request: Request, value: Any, action: RequestAction
    ) -> Any:
        """Serialize tags for display.

        Args:
            request: Starlette request
            value: Field value (list or string)
            action: Current action

        Returns:
            Serialized value

        """
        if value is None:
            return [] if action in ("list", "detail") else ""

        # Convert to list if string
        if isinstance(value, str):
            tags = [tag.strip() for tag in value.split(",") if tag.strip()]
        else:
            tags = value

        # For list/detail view, return as list (will be rendered as badges)
        if action in ("list", "detail"):
            return tags

        # For edit/create, return as comma-separated string
        return ", ".join(tags) if tags else ""


class SlugField(BaseField):
    """Field for URL-safe slugs.

    Validates that slug contains only lowercase letters, digits, and hyphens.
    """

    def __init__(
        self,
        name: str = "slug",
        label: str | None = None,
        placeholder: str = "my-post-slug",
        max_length: int = 100,
        **kwargs: Any,
    ):
        """Initialize slug field.

        Args:
            name: Field name (default: 'slug')
            label: Field label
            placeholder: Placeholder text
            max_length: Maximum length (default: 100)
            **kwargs: Additional field options

        """
        super().__init__(name, label=label, **kwargs)
        self.placeholder = placeholder
        self.max_length = max_length

    async def parse_form_data(
        self, request: Request, form_data: FormData, action: RequestAction
    ) -> Any:
        """Parse and validate slug from form data.

        Args:
            request: Starlette request
            form_data: Form data
            action: Request action

        Returns:
            Validated slug

        Raises:
            ValueError: If slug is invalid

        """
        value = str(form_data.get(self.name, "")).strip().lower()

        if not value:
            return value

        # Validate slug format
        import re

        if not re.match(r"^[a-z0-9][a-z0-9-]{0,99}$", value):
            raise ValueError(
                f"Invalid slug '{value}'. Use only lowercase letters, "
                "digits, and hyphens (max 100 chars)."
            )

        return value

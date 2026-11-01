"""Validated document operations for schema-aware admin writes."""

import pathlib
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from pydantic import ValidationError

from . import helpers, store
from .config import CollectionSpec
from .issues import Issue
from .models import DEFAULT_SCHEMA, FrontmatterSchema
from .validators import Validator, run_blocking


class BlockingValidationError(ValueError):
  """A document failed a configured blocking validator."""

  def __init__(self, issues: list[Issue]):
    self.issues = issues
    super().__init__('Document failed configured validation checks')


@dataclass(frozen=True)
class SaveResult:
  """Details of a successfully saved Markdown document."""

  slug: str
  etag: str
  status: str


class DocumentService:
  """Validate, write and check Markdown documents without an HTTP boundary."""

  def __init__(
    self,
    documents: store.DocumentStore,
    schema: FrontmatterSchema | None = None,
    *,
    collection_spec: CollectionSpec | None = None,
    validators: tuple[Validator, ...] = (),
    cwd: pathlib.Path | None = None,
  ):
    self.documents = documents
    self.schema: FrontmatterSchema = (
      schema
      or (collection_spec.schema if collection_spec is not None else None)
      or DEFAULT_SCHEMA
    )
    self.collection_spec = collection_spec
    self.validators = validators or (
      collection_spec.validators if collection_spec is not None else ()
    )
    self.cwd = cwd or pathlib.Path.cwd()

  def _validated_frontmatter(
    self,
    frontmatter: Mapping[str, Any],
    *,
    is_create: bool,
    existing: Mapping[str, Any] | None = None,
  ) -> dict[str, Any]:
    model = self.schema.model().model_validate(dict(frontmatter))
    return self.schema.dump_for_write(
      model, is_create=is_create, existing=existing
    )

  def _check_unique(
    self,
    slug: str | None,
    frontmatter: Mapping[str, Any],
  ) -> None:
    """Reject duplicate configured values before a write is committed."""
    spec = self.collection_spec
    if spec is None or not spec.unique:
      return
    slug_regex = (
      spec.slug_template.slug_regex()
      if spec.slug_template is not None
      else None
    )
    new_values: dict[str, Any] = {}
    for name in spec.unique:
      if name == 'seq':
        # A generated slug receives its sequence while DocumentStore holds
        # the same lock; manual slugs must be checked against the template.
        if slug is None:
          continue
        match = slug_regex.fullmatch(slug) if slug_regex is not None else None
        if match is None or 'seq' not in match.groupdict():
          raise ValueError(
            'Slug does not match the configured sequence template'
          )
        new_values[name] = match.group('seq')
      else:
        field = self.schema.get(name)
        key = field.key if field is not None else name
        new_values[name] = frontmatter.get(key)
    for other_slug in self.documents.list():
      if other_slug == slug:
        continue
      try:
        existing = self.documents.read(other_slug).frontmatter
      except (store.ParseError, store.NotFoundError):
        continue
      for name, value in new_values.items():
        if value is None or value == '':
          continue
        if name == 'seq':
          match = slug_regex.fullmatch(other_slug) if slug_regex else None
          existing_value = match.group('seq') if match else None
        else:
          field = self.schema.get(name)
          key = field.key if field is not None else name
          existing_value = existing.get(key)
        if existing_value == value:
          raise ValueError(
            f'Value {value!r} of unique field {name!r} is already used '
            f'by {other_slug!r}'
          )

  def _check_blocking(
    self, slug: str, frontmatter: Mapping[str, Any]
  ) -> None:
    if not self.validators:
      return
    path = self.documents.path_for(slug)
    if path is None:
      raise FileNotFoundError(f'Document {slug!r} was not written')
    blocking = run_blocking(
      self.validators,
      collection_name=(
        self.collection_spec.name
        if self.collection_spec is not None
        else self.documents.collection.name
      ),
      slug=slug,
      path=path,
      frontmatter=frontmatter,
      cwd=self.cwd,
    )
    if blocking:
      raise BlockingValidationError(blocking)

  def _rollback(
    self, slug: str, *, previous_text: str | None
  ) -> None:
    path = self.documents.path_for(slug)
    if path is None:
      return
    if previous_text is None:
      # Rollback is not a user-facing delete and must work for delete=False.
      path.unlink(missing_ok=True)
    else:
      store.atomic_write_text(path, previous_text)
    helpers.clear_posts_cache()

  def save(
    self,
    slug: str | None,
    frontmatter: Mapping[str, Any],
    content: str,
    *,
    if_match: str | None = None,
    expected_exists: bool | None = None,
    user: Any = None,
  ) -> SaveResult:
    """Create or update a document after schema and blocking validation.

    An empty slug uses the collection's configured slug template. Updates may
    supply the previously read etag to reject stale forms with HTTP-neutral
    `store.ConflictError` semantics.
    """
    is_generated = not slug
    if not isinstance(content, str) or not content.strip():
      raise ValueError('Document content must not be empty')
    if slug:
      self.documents.path_for(slug)
    if is_generated and (
      self.collection_spec is None
      or self.collection_spec.slug_template is None
    ):
      raise ValueError(
        'A slug is required; configure a collection slug_template '
        'to generate it.'
      )

    body = f'\n{content.rstrip()}\n'
    actor = _actor(user)

    # Keep schema merging, uniqueness checks, the write and any rollback in
    # one critical section. A validator failure must never restore stale bytes
    # over another writer's successful update.
    with self.documents._lock:
      exists = False if is_generated else self.documents.exists(str(slug))
      if expected_exists is not None and exists != expected_exists:
        raise store.ConflictError(
          f'document {slug!r} changed while the form was open',
          status_code=409,
        )
      is_new = is_generated or not exists
      existing: dict[str, Any] | None = None
      previous_text: str | None = None
      if not is_new:
        record = self.documents.read(str(slug))
        existing = record.frontmatter
        path = self.documents.path_for(str(slug))
        previous_text = path.read_text(encoding='utf-8') if path else None

      validated = self._validated_frontmatter(
        frontmatter, is_create=is_new, existing=existing
      )

      if is_generated:
        assert self.collection_spec is not None
        self._check_unique(None, validated)
        slug, etag = self.collection_spec.create_document(
          self.documents,
          validated,
          body,
          created_at=datetime.now(UTC),
          user=actor,
          notify=False,
        )
      else:
        slug = str(slug)
        self._check_unique(slug, validated)
        etag = self.documents.write(
          slug,
          validated,
          body,
          if_match=if_match,
          user=actor,
          notify=False,
        )

      try:
        self._check_blocking(slug, validated)
      except BlockingValidationError:
        self._rollback(slug, previous_text=previous_text)
        raise

    # Hooks run after the transaction is committed and outside the lock.
    self.documents.notify_change(
      'created' if is_new else 'updated',
      slug,
      etag,
      user=actor,
    )
    helpers.clear_posts_cache()
    return SaveResult(
      slug=slug, etag=etag, status='created' if is_new else 'updated'
    )

  def delete(
    self,
    slug: str,
    *,
    if_match: str | None = None,
    user: Any = None,
  ) -> None:
    """Delete a document with the collection's configured restrictions."""
    self.documents.delete(slug, if_match=if_match, user=_actor(user))
    helpers.clear_posts_cache()


def _actor(user: Any) -> Any:
  """Return a stable, non-sensitive actor identifier for change events."""
  if isinstance(user, Mapping):
    return user.get('username') or user.get('id')
  return user

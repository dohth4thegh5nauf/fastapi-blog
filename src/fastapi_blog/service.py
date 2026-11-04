"""Validated document operations for schema-aware admin writes."""

import copy
import dataclasses
import pathlib
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from . import helpers, store
from .config import CollectionSpec
from .i18n_collections import I18nCollection
from .issues import Issue
from .models import DEFAULT_SCHEMA, FrontmatterSchema
from .validators import Validator, run_blocking


class BlockingValidationError(ValueError):
  """A document failed a configured blocking validator."""

  def __init__(self, issues: list[Issue]):
    """Store the findings on the exception for the caller to report."""
    self.issues = issues
    super().__init__('Document failed configured validation checks')


class UniqueViolationError(ValueError):
  """A configured `unique` value is already used by another document."""

  def __init__(self, name: str, value: Any, other_slug: str):
    """Keep the parts on the exception so callers can map them to errors."""
    self.name = name
    self.value = value
    self.other_slug = other_slug
    super().__init__(
      f'Value {value!r} of unique field {name!r} is already used '
      f'by {other_slug!r}'
    )


@dataclass(frozen=True)
class SaveResult:
  """Details of a successfully saved Markdown document."""

  slug: str
  etag: str
  status: str


@dataclass(frozen=True)
class LocalizedSaveResult:
  """Details of a committed multi-locale entry update."""

  slug: str
  etags: Mapping[str, str]
  entry_etag: str
  locales_present: tuple[str, ...]
  status: str
  issues: tuple[Issue, ...] = ()


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
    """Bind the service to a store, schema and validators.

    Args:
        documents: The store the documents are written to.
        schema: Frontmatter schema for validation; defaults to the
            collection spec's schema, then to the built-in schema.
        collection_spec: Optional project collection settings (schema,
            validators, slug template, `unique` constraints).
        validators: Blocking validators; defaults to the collection spec's.
        cwd: Project root used as the validators' working directory.

    """
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
    self.i18n_documents = (
      I18nCollection(
        documents.collection,
        collection_spec.i18n,
        lock=documents._lock,
      )
      if collection_spec is not None and collection_spec.i18n is not None
      else None
    )

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

  def _authorize_document(
    self,
    user: Any,
    action: str,
    slug: str | None,
    locale: str | None,
    before: Mapping[str, Any] | None,
    after: Mapping[str, Any] | None,
  ) -> None:
    """Apply the optional document policy without weakening collection RBAC."""
    policy = (
      self.collection_spec.document_authorize if self.collection_spec else None
    )
    if policy is None:
      return
    result = policy(
      user, action, self.documents.collection.name, slug, locale, before, after
    )
    if result is not True:
      reason = (
        result
        if isinstance(result, str) and result
        else 'Document access denied'
      )
      raise store.OperationNotAllowedError(reason)

  def authorize_read(
    self,
    user: Any,
    slug: str,
    locale: str | None,
    frontmatter: Mapping[str, Any],
  ) -> None:
    """Check document read access using the same policy as writes."""
    self._authorize_document(user, 'read', slug, locale, frontmatter, None)

  def _check_transitions(
    self,
    fields: tuple[Any, ...],
    before: Mapping[str, Any] | None,
    after: Mapping[str, Any],
    *,
    user: Any,
    slug: str | None,
    locale: str | None,
    prefix: str = '',
  ) -> None:
    """Reject unlisted field transitions before modifying any file."""
    old = before or {}
    for field in fields:
      key = field.key
      label = f'{prefix}.{field.name}' if prefix else field.name
      previous = old.get(key)
      current = after.get(key)
      if field.transitions is not None and current != previous:
        if before is None:
          if current not in field.transitions.get('initial', []):
            raise ValueError(
              f'Initial value {current!r} is not allowed for {label!r}'
            )
        else:
          matching = [
            rule
            for rule in field.transitions.get('allowed', [])
            if rule['from'] == previous and rule['to'] == current
          ]
          if not matching:
            raise ValueError(
              f'Transition {previous!r} to {current!r} is not allowed for {label!r}'
            )
          permission = matching[0].get('permission')
          if permission:
            if (
              not self.collection_spec
              or not self.collection_spec.document_authorize
            ):
              raise store.OperationNotAllowedError(
                f'Transition requires permission {permission!r}'
              )
            self._authorize_document(user, permission, slug, locale, old, after)
          self._authorize_document(user, 'transition', slug, locale, old, after)
      if field.type == 'object' and isinstance(current, Mapping):
        self._check_transitions(
          field.fields or (),
          previous if isinstance(previous, Mapping) else None,
          current,
          user=user,
          slug=slug,
          locale=locale,
          prefix=label,
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
    violation = spec.find_unique_violation(self.documents, slug, frontmatter)
    if violation is not None:
      raise UniqueViolationError(*violation)

  def _check_blocking(self, slug: str, frontmatter: Mapping[str, Any]) -> None:
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

  def _rollback(self, slug: str, *, previous_text: str | None) -> None:
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
    if self.i18n_documents is not None:
      raise store.OperationNotAllowedError('Use localized document operations')
    if not isinstance(content, str) or not content.strip():
      raise ValueError('Document content must not be empty')
    if slug:
      self.documents.path_for(slug)
    body = f'\n{content.rstrip()}\n'
    return self.commit(
      slug,
      frontmatter,
      body,
      prepare=lambda is_new, existing: self._validated_frontmatter(
        frontmatter, is_create=is_new, existing=existing
      ),
      if_match=if_match,
      expected_exists=expected_exists,
      user=user,
    )

  def commit(
    self,
    slug: str | None,
    frontmatter: Mapping[str, Any],
    body: str,
    *,
    prepare: Callable[[bool, Mapping[str, Any] | None], Mapping[str, Any]]
    | None = None,
    if_match: str | None = None,
    expected_exists: bool | None = None,
    user: Any = None,
  ) -> SaveResult:
    """Write a document, run the blocking validators, roll back on failure.

    For callers whose frontmatter is already schema-validated (the REST API
    validates its payloads before writing); `save()` validates and delegates
    here. Uniqueness, the store write, the blocking validators and any
    rollback run in one critical section; `on_change` fires after the commit,
    outside the lock.
    """
    is_generated = not slug
    if (
      is_generated
      and self.collection_spec
      and self.collection_spec.document_authorize
    ):
      raise store.OperationNotAllowedError(
        'An explicit slug is required when a document policy is configured'
      )
    if is_generated and (
      self.collection_spec is None or self.collection_spec.slug_template is None
    ):
      raise ValueError(
        'A slug is required; configure a collection slug_template '
        'to generate it.'
      )
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

      validated: dict[str, Any] = (
        dict(prepare(is_new, existing))
        if prepare is not None
        else dict(frontmatter)
      )
      self._authorize_document(
        user, 'create' if is_new else 'update', slug, None, existing, validated
      )
      self._check_transitions(
        self.schema.fields,
        existing,
        validated,
        user=user,
        slug=slug,
        locale=None,
      )

      if is_generated:
        # The is_generated branch above guarantees a spec.
        assert self.collection_spec is not None  # nosec B101
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
    if self.i18n_documents is not None:
      raise store.OperationNotAllowedError('Use localized document operations')
    with self.documents._lock:
      before = self.documents.read(slug).frontmatter
      self._authorize_document(user, 'delete', slug, None, before, None)
      self.documents.delete(slug, if_match=if_match, user=_actor(user))
    helpers.clear_posts_cache()

  def save_localized(
    self,
    slug: str,
    documents: Mapping[str, tuple[Mapping[str, Any], str]],
    *,
    if_match: Mapping[str, str] | str | None = None,
    expected_entry_etag: str | None = None,
    expected_exists: bool | None = None,
    user: Any = None,
  ) -> LocalizedSaveResult:
    """Validate and atomically save one or more locales of an entry."""
    return self.save_many_localized(
      {slug: documents},
      if_match={slug: if_match} if if_match is not None else None,
      expected_entry_etags=(
        {slug: expected_entry_etag} if expected_entry_etag is not None else None
      ),
      expected_exists=(
        {slug: expected_exists} if expected_exists is not None else None
      ),
      user=user,
    )[slug]

  def save_many_localized(
    self,
    entries: Mapping[str, Mapping[str, tuple[Mapping[str, Any], str]]],
    *,
    if_match: Mapping[str, Mapping[str, str] | str] | None = None,
    expected_entry_etags: Mapping[str, str | None] | None = None,
    expected_exists: Mapping[str, bool] | None = None,
    user: Any = None,
  ) -> dict[str, LocalizedSaveResult]:
    """Validate and commit multiple localized entries as one transaction."""
    adapter = self.i18n_documents
    if adapter is None or self.collection_spec is None:
      raise ValueError('This collection does not enable i18n')
    if not entries:
      raise ValueError('At least one localized entry is required')

    config = adapter.config
    canonical_locale = config.default_locale
    prepared: dict[str, dict[str, tuple[dict[str, Any], str]]] = {}
    issues_by_slug: dict[str, list[Issue]] = {slug: [] for slug in entries}
    was_created: dict[str, bool] = {}
    canonical_sources: dict[str, Mapping[str, Any]] = {}

    with self.documents._lock:
      for slug in sorted(entries):
        locale_documents = entries[slug]
        if not locale_documents:
          raise ValueError(f'Entry {slug!r} has no locale documents')
        unknown = set(locale_documents) - set(config.locales)
        if unknown:
          raise ValueError(f'Unknown locale(s): {sorted(unknown)!r}')

        present = set(adapter.locales_present(slug))
        canonical_exists = canonical_locale in present
        if (
          expected_exists is not None
          and slug in expected_exists
          and canonical_exists != expected_exists[slug]
        ):
          raise store.ConflictError(
            f'Entry {slug!r} changed while authorizing the operation',
            status_code=409,
          )
        was_created[slug] = not canonical_exists
        if not canonical_exists and canonical_locale not in locale_documents:
          raise ValueError(
            f'Cannot create translation {slug!r} without its canonical '
            f'{canonical_locale!r} document'
          )

        existing_records: dict[str, Mapping[str, Any]] = {}
        for locale in locale_documents:
          if locale in present:
            existing_records[locale] = adapter.read(
              slug, locale, fallback=False
            ).frontmatter

        canonical_source: Mapping[str, Any]
        canonical_existing = (
          adapter.read(slug, canonical_locale, fallback=False).frontmatter
          if canonical_exists
          else None
        )
        if canonical_locale in locale_documents:
          raw_canonical, _canonical_body = locale_documents[canonical_locale]
          model = self.schema.model().model_validate(dict(raw_canonical))
          canonical_source = self.schema.dump_for_write(
            model,
            is_create=not canonical_exists,
            existing=canonical_existing,
          )
        else:
          assert canonical_existing is not None
          canonical_source = canonical_existing
        canonical_sources[slug] = canonical_source

        prepared_entry: dict[str, tuple[dict[str, Any], str]] = {}
        for locale in sorted(locale_documents):
          raw_frontmatter, body = locale_documents[locale]
          if locale == canonical_locale:
            validated = dict(canonical_source)
          else:
            if locale in existing_records and canonical_existing is not None:
              conflict = self._conflicting_shared_field(
                self.schema.fields, existing_records[locale], canonical_existing
              )
              if conflict is not None:
                raise store.ConflictError(
                  f'Translation {locale!r} contains a conflicting shared '
                  f'field {conflict!r}; resolve it before saving',
                  status_code=409,
                )
            candidate = copy.deepcopy(dict(raw_frontmatter))
            self._apply_duplicate_fields(
              self.schema.fields,
              candidate,
              canonical_source,
              locale=locale,
              slug=slug,
              issues=issues_by_slug[slug],
              write=config.write_duplicates,
            )
            translation_schema = (
              self.schema
              if config.required_in_translations
              else _without_required_fields(self.schema)
            )
            model = translation_schema.model().model_validate(candidate)
            validated = translation_schema.dump_for_write(
              model,
              is_create=False,
              existing=existing_records.get(locale),
            )
            self._strip_shared_fields(
              self.schema.fields,
              validated,
              write_duplicates=config.write_duplicates,
            )
          prepared_entry[locale] = (validated, body)
          before = existing_records.get(locale)
          self._authorize_document(
            user,
            'create' if before is None else 'update',
            slug,
            locale,
            before,
            validated,
          )
          fields = (
            self.schema.fields
            if locale == canonical_locale
            else tuple(
              field for field in self.schema.fields if field.i18n == 'translate'
            )
          )
          self._check_transitions(
            fields, before, validated, user=user, slug=slug, locale=locale
          )
        if not config.translate_body:
          canonical_body = (
            locale_documents[canonical_locale][1]
            if canonical_locale in locale_documents
            else adapter.read(slug, canonical_locale, fallback=False).body
          )
          for locale, (frontmatter, _body) in tuple(prepared_entry.items()):
            if locale != canonical_locale:
              prepared_entry[locale] = (frontmatter, canonical_body)
        for locale, (_frontmatter, body) in prepared_entry.items():
          if not isinstance(body, str) or not body.strip():
            raise ValueError(f'Content for locale {locale!r} must not be empty')
        prepared[slug] = prepared_entry

      self._check_localized_unique(adapter, canonical_sources)

      def validate(
        slug: str,
        locale: str,
        path: pathlib.Path,
        frontmatter: Mapping[str, Any],
      ) -> None:
        if not self.validators:
          return
        blocking = run_blocking(
          self.validators,
          collection_name=(
            self.collection_spec.name if self.collection_spec else 'posts'
          ),
          slug=slug,
          path=path,
          frontmatter=frontmatter,
          cwd=self.cwd,
          locale=locale,
        )
        if blocking:
          raise BlockingValidationError(blocking)

      etags = adapter.save_many(
        prepared,
        if_match=if_match,
        expected_entry_etags=expected_entry_etags,
        validate=validate,
      )
      snapshots = {
        slug: (
          adapter.entry_etag(slug) or '',
          adapter.locales_present(slug),
          tuple(
            adapter.path_for(slug, locale) for locale in sorted(locale_etags)
          ),
        )
        for slug, locale_etags in etags.items()
      }

    helpers.clear_posts_cache()
    result: dict[str, LocalizedSaveResult] = {}
    for slug, locale_etags in etags.items():
      entry_etag, locales_present, changed_paths = snapshots[slug]
      changed_locales = tuple(sorted(locale_etags))
      self.documents.notify_change(
        'created' if was_created[slug] else 'updated',
        slug,
        entry_etag,
        user=_actor(user),
        locale=(changed_locales[0] if len(changed_locales) == 1 else None),
        locales=changed_locales,
        paths=changed_paths,
        entry_etag=entry_etag,
      )
      result[slug] = LocalizedSaveResult(
        slug=slug,
        etags=locale_etags,
        entry_etag=entry_etag,
        locales_present=locales_present,
        status='created' if was_created[slug] else 'updated',
        issues=tuple(issues_by_slug[slug]),
      )
    return result

  def _conflicting_shared_field(
    self,
    fields: tuple[Any, ...],
    translated: Mapping[str, Any],
    canonical: Mapping[str, Any],
    prefix: str = '',
  ) -> str | None:
    """Detect stored shared values that a save would otherwise discard."""
    for field in fields:
      key = field.key if field.key in translated else field.name
      canonical_key = field.key if field.key in canonical else field.name
      label = f'{prefix}.{field.name}' if prefix else field.name
      if field.i18n in ('none', 'duplicate'):
        if key in translated and (
          canonical_key not in canonical
          or translated[key] != canonical[canonical_key]
        ):
          return label
      elif field.type == 'object':
        left, right = translated.get(key), canonical.get(canonical_key)
        if isinstance(left, Mapping):
          conflict = self._conflicting_shared_field(
            field.fields or (),
            left,
            right if isinstance(right, Mapping) else {},
            label,
          )
          if conflict is not None:
            return conflict
      elif field.type == 'list[object]':
        left, right = translated.get(key), canonical.get(canonical_key)
        if isinstance(left, list):
          right = right if isinstance(right, list) else []
          for index, item in enumerate(left):
            if isinstance(item, Mapping):
              corresponding = (
                right[index]
                if index < len(right) and isinstance(right[index], Mapping)
                else {}
              )
              conflict = self._conflicting_shared_field(
                field.fields or (), item, corresponding, f'{label}[{index}]'
              )
              if conflict is not None:
                return conflict
    return None

  def _apply_duplicate_fields(
    self,
    fields: tuple[Any, ...],
    translated: dict[str, Any],
    canonical: Mapping[str, Any],
    *,
    locale: str,
    slug: str,
    issues: list[Issue],
    write: bool,
    prefix: str = '',
  ) -> None:
    """Mirror or compare schema fields marked ``duplicate``."""
    for field in fields:
      key = field.key
      label = f'{prefix}.{field.name}' if prefix else field.name
      translated_key = key if key in translated else field.name
      canonical_key = key if key in canonical else field.name
      if field.i18n == 'duplicate':
        if canonical_key not in canonical:
          continue
        canonical_value = canonical[canonical_key]
        if translated_key in translated and (
          translated[translated_key] != canonical_value
        ):
          issues.append(
            Issue(
              'warning',
              'translation.duplicate_mismatch',
              f'Duplicate field {label!r} in locale {locale!r} differs '
              'from the canonical value',
              slug=slug,
              field=label,
            )
          )
        if write:
          translated[key] = copy.deepcopy(canonical_value)
          if field.name != key:
            translated.pop(field.name, None)
      elif field.type == 'object':
        translated_value = translated.get(translated_key)
        canonical_value = canonical.get(canonical_key)
        if isinstance(translated_value, dict) and isinstance(
          canonical_value, Mapping
        ):
          self._apply_duplicate_fields(
            field.fields or (),
            translated_value,
            canonical_value,
            locale=locale,
            slug=slug,
            issues=issues,
            write=write,
            prefix=label,
          )
      elif field.type == 'list[object]':
        translated_values = translated.get(translated_key)
        canonical_values = canonical.get(canonical_key)
        if isinstance(translated_values, list) and isinstance(
          canonical_values, list
        ):
          for index, translated_item in enumerate(translated_values):
            if index >= len(canonical_values):
              break
            if isinstance(translated_item, dict) and isinstance(
              canonical_values[index], Mapping
            ):
              self._apply_duplicate_fields(
                field.fields or (),
                translated_item,
                canonical_values[index],
                locale=locale,
                slug=slug,
                issues=issues,
                write=write,
                prefix=f'{label}[{index}]',
              )

  def _strip_shared_fields(
    self,
    fields: tuple[Any, ...],
    values: dict[str, Any],
    *,
    write_duplicates: bool,
  ) -> None:
    """Keep canonical-only values out of translation files."""
    for field in fields:
      key = field.key if field.key in values else field.name
      if field.i18n == 'none' or (
        field.i18n == 'duplicate' and not write_duplicates
      ):
        values.pop(key, None)
      elif field.type == 'object' and isinstance(values.get(key), dict):
        self._strip_shared_fields(
          field.fields or (), values[key], write_duplicates=write_duplicates
        )
      elif field.type == 'list[object]' and isinstance(values.get(key), list):
        for item in values[key]:
          if isinstance(item, dict):
            self._strip_shared_fields(
              field.fields or (), item, write_duplicates=write_duplicates
            )

  def _check_localized_unique(
    self,
    adapter: I18nCollection,
    canonical_sources: Mapping[str, Mapping[str, Any]],
  ) -> None:
    """Check collection-wide unique values against canonical documents."""
    spec = self.collection_spec
    if spec is None or not spec.unique:
      return
    candidates: dict[str, dict[str, Any]] = {}
    for slug, frontmatter in canonical_sources.items():
      candidates[slug] = {
        name: spec.unique_value(name, slug=slug, frontmatter=frontmatter)
        for name in spec.unique
      }
      for name, value in candidates[slug].items():
        if name == 'seq' and value is None:
          raise ValueError(
            'Slug does not match the configured sequence template'
          )

    existing_values: dict[str, dict[str, Any]] = {}
    for entry in adapter.list():
      if entry.slug in canonical_sources:
        continue
      existing_values[entry.slug] = {
        name: spec.unique_value(
          name,
          slug=entry.slug,
          frontmatter=entry.canonical.frontmatter,
        )
        for name in spec.unique
      }

    for slug in sorted(candidates):
      for name, value in candidates[slug].items():
        if value is None or value == '':
          continue
        for other_slug, values in sorted(existing_values.items()):
          if values.get(name) == value:
            raise UniqueViolationError(name, value, other_slug)
        for other_slug in sorted(candidates):
          if other_slug < slug and candidates[other_slug].get(name) == value:
            raise UniqueViolationError(name, value, other_slug)

  def delete_locale(
    self,
    slug: str,
    locale: str,
    *,
    cascade: bool = False,
    if_match: str | None = None,
    user: Any = None,
  ) -> None:
    """Delete one translation while preserving other locales."""
    if self.i18n_documents is None:
      raise ValueError('This collection does not enable i18n')
    with self.documents._lock:
      locales_to_delete = (
        self.i18n_documents.locales_present(slug)
        if locale == self.i18n_documents.config.default_locale and cascade
        else (locale,)
      )
      paths_to_delete = tuple(
        self.i18n_documents.path_for(slug, item) for item in locales_to_delete
      )
      for item in locales_to_delete:
        before = self.i18n_documents.read(
          slug, item, fallback=False
        ).frontmatter
        self._authorize_document(user, 'delete', slug, item, before, None)
      self.i18n_documents.delete_locale(
        slug, locale, cascade=cascade, if_match=if_match
      )
      entry_etag = self.i18n_documents.entry_etag(slug)
      self.documents.notify_change(
        'delete_locale',
        slug,
        None,
        user=_actor(user),
        locale=locale,
        locales=tuple(locales_to_delete),
        paths=paths_to_delete,
        entry_etag=entry_etag,
      )
    helpers.clear_posts_cache()

  def rename_localized_entry(
    self,
    old_slug: str,
    new_slug: str,
    *,
    expected_entry_etag: str | None = None,
    user: Any = None,
  ) -> str | None:
    """Rename the canonical slug and move every locale file together."""
    adapter = self.i18n_documents
    if adapter is None:
      raise ValueError('This collection does not enable i18n')
    with self.documents._lock:
      locales = adapter.locales_present(old_slug)
      if old_slug == new_slug:
        return adapter.entry_etag(old_slug)
      for locale in locales:
        before = adapter.read(old_slug, locale, fallback=False).frontmatter
        self._authorize_document(
          user, 'update', old_slug, locale, before, before
        )
      adapter.rename(
        old_slug,
        new_slug,
        expected_entry_etag=expected_entry_etag,
      )
      result = adapter.entry_etag(new_slug)
      self.documents.notify_change(
        'renamed',
        new_slug,
        result,
        user=_actor(user),
        locales=locales,
        paths=tuple(adapter.path_for(new_slug, locale) for locale in locales),
        entry_etag=result,
      )
    helpers.clear_posts_cache()
    return result

  def delete_localized_entry(
    self,
    slug: str,
    *,
    cascade: bool = False,
    expected_entry_etag: str | None = None,
    user: Any = None,
  ) -> None:
    """Delete all locale files for one canonical entry."""
    adapter = self.i18n_documents
    if adapter is None:
      raise ValueError('This collection does not enable i18n')
    with self.documents._lock:
      locales = adapter.locales_present(slug)
      for locale in locales:
        before = adapter.read(slug, locale, fallback=False).frontmatter
        self._authorize_document(user, 'delete', slug, locale, before, None)
      paths = tuple(adapter.path_for(slug, locale) for locale in locales)
      if (
        expected_entry_etag is not None
        and adapter.entry_etag(slug) != expected_entry_etag
      ):
        raise store.ConflictError(
          f'entry etag does not match for {slug!r}', status_code=412
        )
      adapter.delete_entry(slug, cascade=cascade)
      self.documents.notify_change(
        'deleted',
        slug,
        None,
        user=_actor(user),
        locales=locales,
        paths=paths,
        entry_etag=None,
      )
    helpers.clear_posts_cache()


def _actor(user: Any) -> Any:
  """Return a stable, non-sensitive actor identifier for change events."""
  if isinstance(user, Mapping):
    return user.get('username') or user.get('id')
  return user


def _without_required_fields(schema: FrontmatterSchema) -> FrontmatterSchema:
  """Clone a schema with required fields relaxed recursively."""

  def relax(fields: tuple[Any, ...]) -> tuple[Any, ...]:
    return tuple(
      dataclasses.replace(
        field,
        required=False,
        fields=relax(field.fields or ()) if field.fields is not None else None,
      )
      for field in fields
    )

  return FrontmatterSchema(
    fields=relax(schema.fields),
    extra=schema.extra,
    jsonld=schema.jsonld,
    seo=schema.seo,
    published_values=schema.published_values,
  )

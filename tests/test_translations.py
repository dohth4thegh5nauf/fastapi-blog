from fastapi_blog.i18n import (
  Translator,
  get_all_locale_names,
  get_locale_name,
  load_translations,
)


def test_public_blog_translator_reads_nested_sections():
  assert Translator('ru').blog.articles == 'Статьи'


def test_unknown_translation_locale_falls_back_to_english():
  assert load_translations('de')['blog']['articles'] == 'Articles'
  assert get_locale_name('de') == 'de'


def test_bundled_locale_names_are_discoverable():
  assert get_all_locale_names() == {'en': 'English', 'ru': 'Русский'}


def test_localized_schema_text_resolution_order():
  from fastapi_blog.i18n import resolve_localized

  labels = {'en': 'Title', 'ru': 'Заголовок', 'de': 'Titel'}
  assert resolve_localized(labels, 'ru', 'en') == 'Заголовок'
  assert resolve_localized(labels, 'fr', 'en') == 'Title'
  assert resolve_localized(labels, 'fr', 'es') == 'Title'
  assert resolve_localized('Title', 'ru', 'en') == 'Title'


def test_project_translations_overlay_bundled_and_english_fallback(
  tmp_path, caplog
):
  translations_dir = tmp_path / 'translations'
  translations_dir.mkdir()
  (translations_dir / 'de.yaml').write_text(
    'locale:\n  code: de\n  name: Deutsch\npost:\n  title: Titel\n',
    encoding='utf-8',
  )

  with caplog.at_level('WARNING', logger='fastapi_blog.i18n'):
    translations = load_translations('de', translations_dir)

  assert translations['post']['title'] == 'Titel'
  assert translations['blog']['articles'] == 'Articles'
  assert get_locale_name('de', translations_dir) == 'Deutsch'
  assert 'using English fallback' in caplog.text


def test_configured_locale_names_include_unknown_codes(tmp_path):
  names = get_all_locale_names(tmp_path, ['fr', 'de'])
  assert names['en'] == 'English'
  assert names['ru'] == 'Русский'
  assert names['fr'] == 'fr'
  assert names['de'] == 'de'


def test_bundled_english_and_russian_translations_have_complete_key_sets():
  from importlib.resources import files

  import yaml

  from fastapi_blog.i18n import _missing_translation_keys

  english = yaml.safe_load(
    files('fastapi_blog')
    .joinpath('translations/en.yaml')
    .read_text(encoding='utf-8')
  )
  russian = yaml.safe_load(
    files('fastapi_blog')
    .joinpath('translations/ru.yaml')
    .read_text(encoding='utf-8')
  )
  assert _missing_translation_keys(english, russian) == []

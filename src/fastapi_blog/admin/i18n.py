"""Internationalization utilities for admin panel.

Loads translations from YAML files and provides translation functions.
"""

import pathlib
from typing import Any

import yaml


# Cache for loaded translations
_translations_cache: dict[str, dict[str, Any]] = {}


def load_translations(locale: str) -> dict[str, Any]:
    """Load translations for a specific locale from YAML file.

    Args:
      locale: Language code (e.g. 'en', 'ru')

    Returns:
      Dictionary with translations

    Example:
      ```python
      translations = load_translations(
          "ru"
      )
      home_label = (
          translations[
              "nav"
          ]["home"]
      )  # 'Главная'
      ```

    """
    if locale in _translations_cache:
        return _translations_cache[locale]

    # Get path to translations directory
    translations_dir = pathlib.Path(__file__).parent / "translations"
    yaml_file = translations_dir / f"{locale}.yaml"

    if not yaml_file.exists():
        raise FileNotFoundError(f"Translation file not found: {yaml_file}")

    # Load YAML file
    with open(yaml_file, encoding="utf-8") as f:
        translations = yaml.safe_load(f)

    # Cache translations
    _translations_cache[locale] = translations

    return translations


def get_locale_name(locale: str) -> str:
    """Get display name for a locale.

    Args:
      locale: Language code (e.g. 'en', 'ru')

    Returns:
      Display name (e.g. 'English', 'Русский')

    """
    translations = load_translations(locale)
    return translations["locale"]["name"]


def get_all_locale_names() -> dict[str, str]:
    """Get display names for all available locales.

    Returns:
      Dictionary mapping locale codes to display names

    """
    translations_dir = pathlib.Path(__file__).parent / "translations"
    locales = {}

    for yaml_file in translations_dir.glob("*.yaml"):
        locale = yaml_file.stem
        try:
            locales[locale] = get_locale_name(locale)
        except (FileNotFoundError, yaml.YAMLError):
            # Skip invalid translation files
            continue

    return locales


class Translator:
    """Translator class for admin panel.

    Provides convenient access to translations for a specific locale.

    Example:
      ```python
      t = Translator("ru")
      print(
          t.nav.home
      )  # 'Главная'
      print(
          t.user.plural
      )  # 'Пользователи'
      ```

    """

    def __init__(self, locale: str):
        """Initialize translator for a specific locale.

        Args:
          locale: Language code (e.g. 'en', 'ru')

        """
        self.locale = locale
        self._translations = load_translations(locale)

    def __getattr__(self, name: str) -> Any:
        """Get translation section by attribute access.

        Args:
          name: Section name (e.g. 'nav', 'user', 'post')

        Returns:
          TranslationSection object for nested access

        """
        if name in self._translations:
            return TranslationSection(self._translations[name])
        raise AttributeError(f"Translation section not found: {name}")

    def get(self, key: str, default: str | None = None) -> str:
        """Get translation by dot-separated key.

        Args:
          key: Dot-separated key (e.g. 'nav.home', 'user.plural')
          default: Default value if key not found

        Returns:
          Translated string or default value

        """
        parts = key.split(".")
        value = self._translations

        for part in parts:
            if isinstance(value, dict) and part in value:
                value = value[part]
            else:
                return default if default is not None else key

        return (
            value if isinstance(value, str) else default if default is not None else key
        )


class TranslationSection:
    """Wrapper for translation section to enable attribute access.

    Example:
      ```python
      section = TranslationSection(
          {
              "home": "Home",
              "users": "Users",
          }
      )
      print(
          section.home
      )  # 'Home'
      print(
          section.users
      )  # 'Users'
      ```

    """

    def __init__(self, data: dict[str, Any]):
        """Initialize section with translation data.

        Args:
          data: Dictionary with translations

        """
        self._data = data

    def __getattr__(self, name: str) -> Any:
        """Get translation by attribute access.

        Args:
          name: Translation key

        Returns:
          Translated string or nested TranslationSection

        """
        if name in self._data:
            value = self._data[name]
            if isinstance(value, dict):
                return TranslationSection(value)
            return value
        raise AttributeError(f"Translation key not found: {name}")

    def get(self, name: str, default: str | None = None) -> str:
        """Get translation with default value.

        Args:
          name: Translation key
          default: Default value if key not found

        Returns:
          Translated string or default value

        """
        result = self._data.get(name, default)
        return str(result) if result is not None else (default or "")

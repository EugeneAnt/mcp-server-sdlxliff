"""
Language configuration and mapping for spellchecking.

Maps BCP-47 language codes (used in XLIFF/SDLXLIFF files) to spellchecker
configurations. Uses different backends for different languages:
- Yandex Speller: Russian, Ukrainian, English (proper morphology)
- pyspellchecker: German, Spanish, French, Italian, Portuguese, Dutch, etc.
"""

from typing import Optional, Tuple

# Spellcheck backend types
BACKEND_YANDEX = "yandex"
BACKEND_PYSPELLCHECKER = "pyspellchecker"

# Language configuration: maps ISO 639-1 code to (backend, lang_code)
# Yandex supports: ru, uk, en
# pyspellchecker supports: en, de, es, fr, it, pt, ru, nl, lv, eu, fa, ar
LANGUAGE_CONFIG = {
    # Yandex Speller (better morphology for these)
    'ru': (BACKEND_YANDEX, 'ru'),       # Russian
    'uk': (BACKEND_YANDEX, 'uk'),       # Ukrainian
    'en': (BACKEND_YANDEX, 'en'),       # English (Yandex handles it well too)

    # pyspellchecker (adequate for these languages)
    'de': (BACKEND_PYSPELLCHECKER, 'de'),  # German
    'es': (BACKEND_PYSPELLCHECKER, 'es'),  # Spanish
    'fr': (BACKEND_PYSPELLCHECKER, 'fr'),  # French
    'it': (BACKEND_PYSPELLCHECKER, 'it'),  # Italian
    'pt': (BACKEND_PYSPELLCHECKER, 'pt'),  # Portuguese
    'nl': (BACKEND_PYSPELLCHECKER, 'nl'),  # Dutch

    # These have limited quality in pyspellchecker, but available
    # 'lv': (BACKEND_PYSPELLCHECKER, 'lv'),  # Latvian - disabled, poor quality
    # 'eu': (BACKEND_PYSPELLCHECKER, 'eu'),  # Basque - disabled, poor quality
    # 'fa': (BACKEND_PYSPELLCHECKER, 'fa'),  # Persian - disabled, poor quality
    # 'ar': (BACKEND_PYSPELLCHECKER, 'ar'),  # Arabic - disabled, poor quality
}


def get_spellcheck_config(xliff_lang: str) -> Optional[Tuple[str, str]]:
    """
    Get spellcheck backend and language code for an XLIFF language.

    Args:
        xliff_lang: BCP-47 language tag (e.g., 'de-DE', 'en-US', 'ru-RU')

    Returns:
        Tuple of (backend, lang_code) or None if unsupported
        Example: ('yandex', 'ru') or ('pyspellchecker', 'de')
    """
    if not xliff_lang:
        return None
    # Extract base language code (e.g., 'ru-RU' -> 'ru')
    base_lang = xliff_lang.split('-')[0].lower()
    return LANGUAGE_CONFIG.get(base_lang)


def is_language_supported(xliff_lang: str) -> bool:
    """
    Check if language is supported for spellchecking.

    Args:
        xliff_lang: BCP-47 language tag (e.g., 'de-DE', 'en-US')

    Returns:
        True if the language is supported by any spellcheck backend
    """
    return get_spellcheck_config(xliff_lang) is not None


# Kept for backwards compatibility
def xliff_to_spellcheck_lang(xliff_lang: str) -> Optional[str]:
    """
    Convert XLIFF BCP-47 language code to spellchecker language code.

    Deprecated: Use get_spellcheck_config() instead.
    """
    config = get_spellcheck_config(xliff_lang)
    return config[1] if config else None
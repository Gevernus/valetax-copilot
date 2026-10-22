"""Language detection: deterministic and local (lingua), not a model judgment."""

from functools import cache

from lingua import Language, LanguageDetector, LanguageDetectorBuilder

# Languages a Valetax support queue plausibly sees; a closed set is faster and more accurate.
_LANGUAGES = (
    Language.ENGLISH, Language.RUSSIAN, Language.SPANISH, Language.PORTUGUESE, Language.ARABIC,
    Language.INDONESIAN, Language.MALAY, Language.VIETNAMESE, Language.THAI, Language.TURKISH,
    Language.FRENCH, Language.GERMAN, Language.HINDI, Language.CHINESE, Language.UKRAINIAN,
)  # fmt: skip


@cache
def _detector() -> LanguageDetector:
    return LanguageDetectorBuilder.from_languages(*_LANGUAGES).build()


def detect_language(text: str) -> str:
    """ISO 639-1 code; English when the text is too short or mixed to tell."""
    found = _detector().detect_language_of(text)
    return found.iso_code_639_1.name.lower() if found else "en"

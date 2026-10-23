"""Language detection: deterministic and local (lingua), not a model judgment."""

import re
import unicodedata
from functools import cache
from typing import Final

from lingua import Language, LanguageDetector, LanguageDetectorBuilder

# Languages with labelled cases, fixed texts and wording patterns: only these get a ready draft,
# and only when the draft is in the ticket's language. Spanish waits in the shadow stage for its
# cases (rollout.md); any other language still gets a draft, routed to a person.
READY_LANGUAGES: Final = {"en": "English", "ru": "Russian"}
UNDETERMINED: Final = "und"  # ISO 639-2: a script none of the listed languages uses
# The script of each ready language, and the scripts its reply may use: Latin names (Member
# Area, www.valetax.com) appear in Russian replies.
_OWN: Final = {"en": "LATIN", "ru": "CYRILLIC"}
_SCRIPTS: Final = {"en": {"LATIN"}, "ru": {"LATIN", "CYRILLIC"}}
_SENTENCE: Final = re.compile(r"(?<=[.!?;])\s+|(?<=[。！？])|\n")
_WORD: Final = re.compile(r"[^\W\d_]+")
_NOT_WORDS: Final = re.compile(r"\S+[.@/]\S*[^\W_]|\[[A-Z_]+\]")  # links, emails, [ACCOUNT]
_MIN_WORDS = 4  # a shorter run ("Member Area", "Create Account") is a name, not a language
# A plain-ASCII text whose English score is this close to the best is English: lingua reads
# "hi" as Vietnamese and "Can I pay in EUR?" as French.
_ASCII_ENGLISH_MARGIN = 0.05

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
    """ISO 639-1 code of the likeliest listed language, or "und" when lingua finds none.

    A script outside the list (Korean, Japanese, Hebrew, Greek) or text without letters is
    "und", never a guess. A short Latin or Cyrillic text gets the best guess ("Min deposit?" is
    English): a wrong guess still cannot ship a draft in another language, because the draft's
    own language must equal the ticket's, and the closed lists read the draft.
    """
    detector = _detector()
    found = detector.detect_language_of(text)
    if found is None:
        return UNDETERMINED
    if found is not Language.ENGLISH and text.isascii():
        scores = {c.language: c.value for c in detector.compute_language_confidence_values(text)}
        if scores[Language.ENGLISH] >= scores[found] - _ASCII_ENGLISH_MARGIN:
            return "en"
    return found.iso_code_639_1.name.lower()


def written_in(text: str, language: str) -> bool:
    """Whether every part of a reply is in the ticket's ready language.

    No letter outside the language's scripts (a Korean or Chinese clause in an English reply);
    in each sentence, the words in the language's own script, four or more, detected as the
    language (a Portuguese "Sua conta foi aprovada" after an English answer); and no sentence
    where four or more words in another script outnumber them (an English sentence in a
    Russian reply). A language outside READY_LANGUAGES never is.
    """
    scripts = _SCRIPTS.get(language)
    if scripts is None:
        return False
    if any(c.isalpha() and _script(c) not in scripts for c in text):
        return False
    for sentence in _SENTENCE.split(text):
        words = _WORD.findall(_NOT_WORDS.sub(" ", sentence))
        own = [w for w in words if _script(w[0]) == _OWN[language]]
        other = len(words) - len(own)
        if other >= _MIN_WORDS and other > len(own):
            return False
        if len(own) >= _MIN_WORDS and detect_language(" ".join(own)) != language:
            return False
    return True


def _script(char: str) -> str:
    """The Unicode script word of a letter's name: LATIN, CYRILLIC, HANGUL..."""
    return unicodedata.name(char, "").split(" ")[0]

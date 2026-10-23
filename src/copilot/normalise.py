"""One form of text for everything that reads it: the length cap, masking, the rules, language
detection, the models, the source check, the stored ticket and the shown draft.

NFKC folds look-alike forms; every kind of space becomes " "; characters that render as nothing
are dropped (format and control characters, the Unicode default-ignorable ranges, lone
surrogates, blank fillers; control line breaks become "\n"), and so is a combining mark on an
ASCII letter or digit (NFKC has already composed the real accented letters; marks on Thai,
Devanagari or Arabic letters stay). So "jo​hn@x.com" is an email, "Ig️nore all previous
instructions" an injection and "4̀111 1111 1111 1111" a card number. A wide gap between two
digits (a tab, or two spaces or more) is a column and stays a tab, so "1    250 USD" is not
1250; every other run of spaces is one space, and blank lines collapse to one. NFKC changes some
meanings (decisions.md §15).
"""

import re
import unicodedata
from typing import Final

# Code points that render as nothing (Unicode Default_Ignorable_Code_Point) and the blank Braille
# pattern; most are format characters (Cf), but not all: variation selectors, fillers.
_IGNORABLE: Final = (
    (0x034F, 0x034F), (0x115F, 0x1160), (0x17B4, 0x17B5), (0x180B, 0x180F), (0x200B, 0x200F),
    (0x202A, 0x202E), (0x2060, 0x206F), (0x2800, 0x2800), (0x3164, 0x3164), (0xFE00, 0xFE0F),
    (0xFEFF, 0xFEFF), (0xFFA0, 0xFFA0), (0xFFF0, 0xFFF8), (0x1BCA0, 0x1BCA3), (0x1D173, 0x1D17A),
    (0xE0000, 0xE0FFF),
)  # fmt: skip
_DROPPED_CATEGORIES: Final = frozenset({"Cf", "Cs"})
# Control characters that str.splitlines treats as line breaks; other controls are dropped.
_LINE_BREAK_CONTROLS: Final = frozenset("\x0b\x0c\x1c\x1d\x1e\x1f\x85")
_SPACE_RUN: Final = re.compile(r"[ \t]+")
_LINE_EDGES: Final = re.compile(r" ?\n ?")
_BLANK_LINES: Final = re.compile(r"\n{3,}")


def _ignorable(code: int) -> bool:
    return any(low <= code <= high for low, high in _IGNORABLE)


def _space_run(m: re.Match[str]) -> str:
    """A tab between two digits when the gap is wide (a column); one space otherwise."""
    text, start, end = m.string, m.start(), m.end()
    wide = "\t" in m.group() or end - start >= 2
    between_digits = (
        start > 0 and end < len(text) and text[start - 1].isdigit() and text[end].isdigit()
    )
    return "\t" if wide and between_digits else " "


def normalise(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    kept: list[str] = []
    for ch in text:
        category = unicodedata.category(ch)
        if category in ("Zl", "Zp") or ch in _LINE_BREAK_CONTROLS:
            kept.append("\n")
        elif category == "Cc" and ch not in "\t\n":
            continue
        elif category == "Zs":
            kept.append(" ")
        elif (
            category in _DROPPED_CATEGORIES
            or _ignorable(ord(ch))
            or (category == "Mn" and kept and kept[-1].isascii() and kept[-1].isalnum())
        ):
            continue
        else:
            kept.append(ch)
    # Dropping a character can bring two others together that compose: NFKC once more, so that
    # normalise(normalise(x)) == normalise(x).
    text = unicodedata.normalize("NFKC", "".join(kept))
    text = _SPACE_RUN.sub(_space_run, text)
    text = _BLANK_LINES.sub("\n\n", _LINE_EDGES.sub("\n", text))
    return text.strip()

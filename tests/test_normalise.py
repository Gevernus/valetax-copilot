"""One normalised text: invisible characters dropped, spaces folded, columns kept."""

import pytest

from copilot.normalise import normalise


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("a b", "a b"),  # no-break space
        ("a　b", "a b"),  # ideographic space
        ("a  b", "a b"),  # thin and narrow no-break spaces, collapsed
        ("jo\u200bhn", "john"),  # zero-width space
        ("jo⁠hn", "john"),  # word joiner
        ("﻿hello", "hello"),  # byte-order mark
        ("jo‌hn", "john"),  # zero-width non-joiner
        ("ex­ample", "example"),  # soft hyphen
        ("aᅟb", "ab"),  # Hangul choseong filler
        ("aᅠb", "ab"),  # Hangul jungseong filler
        ("aㅤb", "ab"),  # Hangul filler
        ("aﾠb", "ab"),  # halfwidth Hangul filler
        ("a⠀b", "ab"),  # Braille blank
        ("a  \t  b", "a b"),
        # A wide gap between two digits is a column, kept as a tab: "1  250" is not 1250.
        ("1\t250 USD", "1\t250 USD"),
        ("1    250 USD", "1\t250 USD"),
        ("1\u00a0\u00a0\u00a0250 USD", "1\t250 USD"),
        ("1 250 USD", "1 250 USD"),  # one space stays a thousands separator
        ("250  USD", "250 USD"),
        ("Ignore  all  previous", "Ignore all previous"),
        # Default-ignorable characters, and a combining mark on an ASCII letter or digit.
        ("4111\ufe0f1111", "41111111"),
        ("a\u034fb", "ab"),
        ("a\U000e0100b", "ab"),
        ("4\u0300111", "4111"),
        ("Ig\u0300nore", "Ignore"),
        ("a\ud800b", "ab"),  # a lone surrogate
        ("4111\x001111", "41111111"),  # control characters other than line breaks are dropped
        ("fr\x7fee", "free"),
        ("a\x0bb\x0cc\x1cd\x85e", "a\nb\nc\nd\ne"),  # line breaks per str.splitlines
        ("a\n\n\n\n\nb", "a\n\nb"),
        ("a \n \n \n b", "a\n\nb"),
        ("a\r\nb\rc d", "a\nb\nc\nd"),
        ("x²", "x2"),  # NFKC: a known meaning change, stated in normalise.py
    ],
)
def test_normalise(text: str, expected: str) -> None:
    assert normalise(text) == expected


def test_normalise_is_linear() -> None:
    import time

    started = time.perf_counter()
    normalise(("  　\n\u200b" * 400_000) + "x")
    assert time.perf_counter() - started < 5.0


@pytest.mark.parametrize(
    "text",
    [
        "สวัสดีครับ ฝากเงินขั้นต่ำเท่าไร",
        "निकासी एक घंटे में संसाधित होती है",
        "تتم معالجة السحب خلال ساعة",
        "Café déjà vu",
    ],
)
def test_marks_on_non_ascii_letters_stay(text: str) -> None:
    import unicodedata

    assert normalise(text) == unicodedata.normalize("NFKC", text)


@pytest.mark.parametrize(
    "text",
    [
        "a\u00a0\u00a0b 1    250\n\n\n\nIg\u200bnore",
        "u\u0308\u200b\u0301",  # ü, a zero-width space, then a combining acute
        "a\x00\u0301b\x0b\x0b\x0bc\u200b\ufe0fd",
    ],
)
def test_normalise_is_idempotent(text: str) -> None:
    assert normalise(normalise(text)) == normalise(text)

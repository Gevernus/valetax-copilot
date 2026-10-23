"""PII is masked in the normalised text, in linear time."""

import gc
import time

import pytest

from copilot.masking import mask_pii


@pytest.mark.parametrize(
    ("text", "kind"),
    [
        ("write to john.doe+fx@mail.example.com please", "EMAIL"),
        ("card 4111 1111 1111 1111 was charged", "CARD"),
        ("card 4111-1111-1111-1111 was charged", "CARD"),
        ("IBAN DE89 3704 0044 0532 0130 00", "IBAN"),
        ("sent to TQrZ8tKfjaBZXBu9FMbVVkVpS9QS2T5u7K yesterday", "WALLET"),
        ("wallet 0x52908400098527886E0F7030069857D2E4169EE7", "WALLET"),
        ("call me at +62 812 3456 7890", "PHONE"),
        ("my MT5 account 51234567 is blocked", "ACCOUNT"),
        ("логин 8812345, не могу войти", "ACCOUNT"),
        ("reference 123456789012", "NUMBER"),
    ],
)
def test_masks_each_kind(text: str, kind: str) -> None:
    masked = mask_pii(text)
    assert f"[{kind}]" in masked.text
    assert masked.counts.get(kind) == 1


def test_raw_values_do_not_survive() -> None:
    text = "Account 51234567, card 4111111111111111, mail a@b.co, phone +44 20 7946 0958"
    masked = mask_pii(text).text
    for raw in ("51234567", "4111111111111111", "a@b.co", "7946"):
        assert raw not in masked


def test_amounts_and_durations_are_kept() -> None:
    # The grounding check compares numbers, so masking must not eat the ones that matter.
    text = "I deposited 500 USD 3 days ago, min deposit is 8 USD, leverage 1:2000"
    assert mask_pii(text).text == text


def test_card_like_number_failing_luhn_is_not_called_a_card() -> None:
    masked = mask_pii("order 1234567890123")
    assert "[CARD]" not in masked.text
    assert "[NUMBER]" in masked.text


def test_masking_is_linear_on_long_runs() -> None:
    def seconds(n: int) -> float:
        text = "1" * n + " " + "a." * n + " account" + " " * n + "1"
        started = time.perf_counter()
        mask_pii(text)
        return time.perf_counter() - started

    gc.collect()
    gc.disable()  # a full collection over other tests' objects would dominate the timing
    try:
        small, large = (min(seconds(n) for _ in range(3)) for n in (5_000, 20_000))
    finally:
        gc.enable()
    assert large < 2.0
    assert large < 10 * max(small, 0.01)  # 4x the input, not 16x the time


@pytest.mark.parametrize(
    "text",
    ["account:\n123456", "Login:\n\n123456", "логин:\n654321", "my id\n12345",
     "Account No.: 123456"],
)  # fmt: skip
def test_account_numbers_across_a_line_break(text: str) -> None:
    assert "[ACCOUNT]" in mask_pii(text).text


def test_mask_pii_normalises_first() -> None:
    assert "[EMAIL]" in mask_pii("write to jo\u200bhn@x.com").text


def test_a_card_split_by_nul_is_masked() -> None:
    assert mask_pii("4111\x001111\x001111\x001111").counts == {"CARD": 1}

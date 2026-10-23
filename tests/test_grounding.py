"""A draft's figures and fee claims must be in the sections it cites."""

import time

import pytest

from copilot import terms
from copilot.draft import Draft
from copilot.grounding import check_draft
from copilot.kb import KnowledgeBase, load_kb


@pytest.fixture(scope="module")
def kb() -> KnowledgeBase:
    return load_kb()


def draft(reply: str, *citations: str) -> Draft:
    return Draft(abstain=False, reply=reply, citations=list(citations))


def test_number_from_cited_section_passes(kb: KnowledgeBase) -> None:
    d = draft(
        "The minimum deposit starts from 8 USD, depending on the account type.",
        "funding.min-deposit",
    )
    assert check_draft(d, kb, "what is the minimum deposit?").ok


def test_number_not_in_cited_section_fails(kb: KnowledgeBase) -> None:
    d = draft("The minimum deposit is 10 USD.", "funding.min-deposit")
    result = check_draft(d, kb, "what is the minimum deposit?")
    assert not result.ok
    assert "10 USD" in result.problems[0]


def test_number_from_an_uncited_section_fails(kb: KnowledgeBase) -> None:
    # 48 hours is in open.time, but the draft cites only the deposit FAQ.
    d = draft("Verification takes 48 hours.", "funding.min-deposit")
    assert not check_draft(d, kb, "how long is verification?").ok


def test_number_echoed_from_ticket_is_shown_but_marked(kb: KnowledgeBase) -> None:
    d = draft(
        "Your request from 3 days ago is in queue and in the midst of getting processed.",
        "funding.withdrawal-pending",
    )
    result = check_draft(d, kb, "my withdrawal is pending for 3 days")
    assert result.ok
    assert result.client_figures == ("3 days",)


def test_ticket_does_not_support_a_policy_figure(kb: KnowledgeBase) -> None:
    # The ticket says "3 days ago"; "3 business days" is a processing time nobody stated.
    d = draft("Withdrawals are processed within 3 business days.", "funding.withdrawal-pending")
    result = check_draft(d, kb, "I requested a withdrawal 3 days ago")
    assert not result.ok
    assert any("3 business days" in p for p in result.problems)


def test_thousands_are_not_supported_by_a_one(kb: KnowledgeBase) -> None:
    d = draft("The minimum deposit starts from $1,000.", "funding.min-deposit")
    assert not check_draft(d, kb, "minimum deposit? I have $1 left").ok


def test_spelled_out_number_is_checked(kb: KnowledgeBase) -> None:
    d = draft("Withdrawals take two business days.", "funding.withdrawal-pending")
    assert not check_draft(d, kb, "how long do withdrawals take?").ok


def test_number_bound_to_another_unit_fails(kb: KnowledgeBase) -> None:
    # 48 is in open.time, as hours.
    d = draft("Verification is completed within 48 days.", "open.time")
    assert not check_draft(d, kb, "how long is verification?").ok


def test_policy_claim_echoed_from_ticket_is_marked(kb: KnowledgeBase) -> None:
    d = draft("Your deposit is guaranteed.", "funding.how-to-deposit")
    result = check_draft(d, kb, "your agent said my deposit is guaranteed, right?")
    assert result.ok
    assert result.client_figures == ("guaranteed",)


def test_a_fee_word_from_the_client_is_still_withheld(kb: KnowledgeBase) -> None:
    # Fees are a closed world: the client asking about one does not let the draft state one.
    d = draft("Deposits are free of charge.", "funding.how-to-deposit")
    result = check_draft(d, kb, "your agent said deposits are free of charge, right?")
    assert any("fee" in p for p in result.problems)


def test_invented_time_without_a_digit_fails(kb: KnowledgeBase) -> None:
    d = draft(
        "Withdrawals are usually processed within a business day.", "funding.withdrawal-pending"
    )
    result = check_draft(d, kb, "how long do withdrawals take?")
    assert any("time units" in p and "business days" in p for p in result.problems)


def test_time_unit_in_other_language_is_matched(kb: KnowledgeBase) -> None:
    d = draft("Баланс обновится в течение 60 минут.", "funding.credit-time")
    assert check_draft(d, kb, "когда зачислят депозит?").ok


def test_fee_claim_fails(kb: KnowledgeBase) -> None:
    d = draft("Deposits are free of charge.", "funding.how-to-deposit")
    assert not check_draft(d, kb, "are there fees?").ok


@pytest.mark.parametrize(
    "link",
    [
        "valetax.co",  # a prefix of the KB's domain, not the domain
        "etax.com",
        "valetax.com/pay",  # not under a KB page
        "valetax.com/how-to-deposit/../../evil",
        "валетакс.com",  # other letters before a Latin top-level domain
        "оплата-валетакс.рф",
        "valetax-pay\u3002net",  # an ideographic full stop
    ],
)
def test_a_link_counts_only_as_a_kb_link_or_its_path_prefix(kb: KnowledgeBase, link: str) -> None:
    result = check_draft(draft(f"Deposit at {link} today.", "funding.how-to-deposit"), kb, "how?")
    assert any("links not in cited sections" in p for p in result.problems), result.problems


@pytest.mark.parametrize(
    "reply",
    [
        "Visit www.valetax.com and log in.",
        "See https://valetax.com/how-to-deposit/ for the steps.",
        "Log in at valetax.com.",
        "Войдите в кабинет, т.е. в Member Area.",
    ],
)
def test_kb_links_and_abbreviations_pass(kb: KnowledgeBase, reply: str) -> None:
    result = check_draft(draft(reply, "funding.how-to-deposit", "open.steps"), kb, "how?")
    assert not [p for p in result.problems if "links" in p], result.problems


@pytest.mark.parametrize(
    "reply",
    [
        "Войдите в личный кабинет.Затем выберите способ оплаты и сумму.",
        "Log in to your Member Area.Затем выберите способ оплаты.",
    ],
)
def test_words_joined_by_a_full_stop_are_not_a_link(kb: KnowledgeBase, reply: str) -> None:
    # A look-alike domain mixes scripts inside one part; whole words in two scripts do not.
    assert check_draft(draft(reply, "funding.how-to-deposit"), kb, "как пополнить счёт?").ok


def test_unknown_or_missing_citation_fails(kb: KnowledgeBase) -> None:
    assert not check_draft(draft("Hello."), kb, "hi").ok
    assert not check_draft(draft("Hello.", "no.such-section"), kb, "hi").ok


def test_trading_advice_in_reply_fails(kb: KnowledgeBase) -> None:
    d = draft("We recommend you buy gold while it is low.", "open.leverage")
    assert not check_draft(d, kb, "should I buy gold?").ok


def test_numbered_list_is_not_a_claim(kb: KnowledgeBase) -> None:
    d = draft(
        "1. Log in to your member area.\n2. Select the preferred payment option.",
        "funding.how-to-deposit",
    )
    assert check_draft(d, kb, "how do I deposit?").ok


def test_abstention_passes(kb: KnowledgeBase) -> None:
    d = Draft(abstain=True, abstain_reason="fees are not in the knowledge base")
    assert check_draft(d, kb, "what are the fees?").ok


@pytest.mark.parametrize(
    "reply",
    [
        "The minimum deposit is USD500.",
        "El depósito mínimo es de 8 €.",
        "The minimum deposit is 8 USDT.",
        "The minimum deposit starts from 8.",  # the source says 8 USD
    ],
)
def test_currency_must_match_the_source(kb: KnowledgeBase, reply: str) -> None:
    assert not check_draft(draft(reply, "funding.min-deposit"), kb, "minimum deposit?").ok


@pytest.mark.parametrize(
    ("reply", "citations"),
    [
        ("A fee of 2 AUD applies to each deposit.", ["deposit.steps"]),
        ("The fee is 3 pounds.", ["open.steps"]),
        ("Deposits are credited within a business day.", ["funding.credit-time"]),
        ("Вывод средств обрабатывается в течение часа.", ["funding.withdrawal-pending"]),
    ],
)
def test_invented_amounts_and_timelines_are_withheld(
    kb: KnowledgeBase, reply: str, citations: list[str]
) -> None:
    assert not check_draft(draft(reply, *citations), kb, "question").ok


@pytest.mark.parametrize(
    "reply",
    [
        "Step 1: Log in to your Member Area. Step 2: Select your preferred payment channel.",
        "2-й шаг: выберите способ оплаты.",
        "Follow steps 1-4 below.",
    ],
)
def test_step_lists_pass(kb: KnowledgeBase, reply: str) -> None:
    assert check_draft(draft(reply, "deposit.steps"), kb, "how do I deposit?").ok


@pytest.mark.parametrize(
    "reply",
    [
        "Добро пожаловать! Чтобы добавить способ оплаты, войдите в личный кабинет.",
        "Buenos días. Puede depositar desde el Área de miembros.",
        "Good day, thanks for your message. You may log in to your member area to deposit.",
    ],
)
def test_greetings_are_not_time_claims(kb: KnowledgeBase, reply: str) -> None:
    assert check_draft(draft(reply, "funding.how-to-deposit"), kb, "how to deposit?").ok


def test_open_steps_count_is_supported(kb: KnowledgeBase) -> None:
    d = draft("You can open an account in 3 simple steps.", "open.steps")
    assert check_draft(d, kb, "how do I open an account?").ok


@pytest.mark.parametrize(
    "reply",
    [
        "Our 24/7 support team can help. The minimum deposit starts from 8 USD.",
        "Log in to MT5 and enable 2FA. The minimum deposit starts from 8 USD.",
        "Your bank must support 3DS. The minimum deposit starts from 8 USD.",
    ],
)
def test_product_names_with_digits_are_not_claims(kb: KnowledgeBase, reply: str) -> None:
    assert check_draft(draft(reply, "funding.min-deposit"), kb, "min deposit?").ok


@pytest.mark.parametrize(
    "text",
    ["a" * 8000, "a-" * 4000, "a." * 4000, "a@" * 4000, "a.a-" * 2000, "a:/" * 2666, "aé" * 4000],
)
def test_link_and_name_scans_are_linear_on_adversarial_text(text: str) -> None:
    # Twice the reply cap; a backtracking pattern took minutes on "a-" * 2000.
    started = time.perf_counter()
    terms.unsupported_links(text, "")
    terms.names(text), terms.policy_words(text), terms.topics(text)
    assert time.perf_counter() - started < 1.0

import pytest
from evals.run_drafts import load_drafts

from copilot import rules
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
    d = draft("Deposits are free of charge.", "funding.how-to-deposit")
    result = check_draft(d, kb, "your agent said deposits are free of charge, right?")
    assert result.ok
    assert result.client_figures == ("free of charge",)


def test_invented_time_without_a_digit_fails(kb: KnowledgeBase) -> None:
    d = draft(
        "Withdrawals are usually processed within a business day.", "funding.withdrawal-pending"
    )
    result = check_draft(d, kb, "how long do withdrawals take?")
    assert any("1 business day" in p for p in result.problems)


def test_time_unit_in_other_language_is_matched(kb: KnowledgeBase) -> None:
    d = draft("Баланс обновится в течение 60 минут.", "funding.credit-time")
    assert check_draft(d, kb, "когда зачислят депозит?").ok


def test_fee_claim_fails(kb: KnowledgeBase) -> None:
    d = draft("Deposits are free of charge.", "funding.how-to-deposit")
    assert not check_draft(d, kb, "are there fees?").ok


def test_unknown_or_missing_citation_fails(kb: KnowledgeBase) -> None:
    assert not check_draft(draft("Hello."), kb, "hi").ok
    assert not check_draft(draft("Hello.", "no.such-section"), kb, "hi").ok


def test_trading_advice_in_reply_fails(kb: KnowledgeBase) -> None:
    d = draft("We recommend you buy gold while it is low.", "open.leverage")
    assert not check_draft(d, kb, "should I buy gold?").ok


def test_decision_fails_in_any_draft(kb: KnowledgeBase) -> None:
    # Answer mode too: the KYC flag may have been missed.
    d = draft("Your account has been verified, you can withdraw now.", "verify.steps")
    result = check_draft(d, kb, "is my account verified yet?")
    assert any("decision" in p for p in result.problems)


@pytest.mark.parametrize(
    ("reply", "kind"),
    [
        ("Your withdrawal has been rejected.", "decision"),
        ("Your account is verified.", "decision"),
        ("We've successfully verified your account.", "decision"),
        ("Your withdrawal is now approved.", "decision"),
        ("Мы одобрили вашу заявку.", "decision"),
        ("Ваш счёт разблокирован.", "decision"),
        ("Мы вернём вам средства.", "decision"),
        ("Su retiro fue aprobado.", "decision"),
        ("Hemos aprobado su solicitud.", "decision"),
        ("Your account is under compliance review.", "compliance"),
        ("This is part of an AML check.", "compliance"),
        ("Ваш счёт проверяет служба безопасности.", "compliance"),
        ("Estamos revisando el origen de sus fondos.", "compliance"),
        ("Your case has been passed to the responsible team.", "passed on"),
        ("We have forwarded your request.", "passed on"),
        ("Ваша жалоба передана ответственной команде.", "passed on"),
        ("Hemos trasladado su caso.", "passed on"),
    ],
)
def test_plain_wordings_are_caught_by_the_patterns(
    kb: KnowledgeBase, reply: str, kind: str
) -> None:
    result = check_draft(draft(reply, "funding.withdrawal-pending"), kb, "status?")
    assert any(kind in p for p in result.problems)


def test_patterns_raise_no_false_alarm_on_labelled_drafts() -> None:
    # The patterns are the cheap first layer and must be precise; the reply questions
    # (classify/questions.py: REPLY) take the paraphrases. Measured in evals/run_drafts.py.
    checks = {
        "decision": rules.announces_decision,
        "check": rules.tips_off,
        "handover": rules.claims_handover,
    }
    false_alarms = [
        (row["id"], label)
        for row in load_drafts()
        for label, check in checks.items()
        if check(row["text"]) and not row[label]
    ]
    assert false_alarms == []


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
        ("The minimum deposit is 3 BTC.", ["deposit.steps"]),
        ("Account opening takes up to 4 working hours.", ["open.steps", "open.time"]),
        ("Deposits are credited within a business day.", ["funding.credit-time"]),
    ],
)
def test_unknown_units_and_spelled_units_are_not_supported_by_step_numbers(
    kb: KnowledgeBase, reply: str, citations: list[str]
) -> None:
    assert not check_draft(draft(reply, *citations), kb, "question").ok


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

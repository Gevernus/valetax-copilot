import pytest

from copilot.draft import Draft, Mode
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
    assert check_draft(d, kb, "what is the minimum deposit?", Mode.ANSWER).ok


def test_number_not_in_cited_section_fails(kb: KnowledgeBase) -> None:
    d = draft("The minimum deposit is 10 USD.", "funding.min-deposit")
    result = check_draft(d, kb, "what is the minimum deposit?", Mode.ANSWER)
    assert not result.ok
    assert "10" in result.problems[0]


def test_number_from_an_uncited_section_fails(kb: KnowledgeBase) -> None:
    # 48 hours is in open.time, but the draft cites only the deposit FAQ.
    d = draft("Verification takes 48 hours.", "funding.min-deposit")
    assert not check_draft(d, kb, "how long is verification?", Mode.ANSWER).ok


def test_number_echoed_from_ticket_passes(kb: KnowledgeBase) -> None:
    d = draft(
        "Your request from 3 days ago is in queue and in the midst of getting processed.",
        "funding.withdrawal-pending",
    )
    assert check_draft(d, kb, "my withdrawal is pending for 3 days", Mode.ANSWER).ok


def test_invented_time_unit_fails(kb: KnowledgeBase) -> None:
    d = draft(
        "Withdrawals are usually processed within a business day.", "funding.withdrawal-pending"
    )
    result = check_draft(d, kb, "how long do withdrawals take?", Mode.ANSWER)
    assert any("time units" in p for p in result.problems)


def test_time_unit_in_other_language_is_matched(kb: KnowledgeBase) -> None:
    d = draft("Баланс обновится в течение 60 минут.", "funding.credit-time")
    assert check_draft(d, kb, "когда зачислят депозит?", Mode.ANSWER).ok


def test_fee_claim_fails(kb: KnowledgeBase) -> None:
    d = draft("Deposits are free of charge.", "funding.how-to-deposit")
    assert not check_draft(d, kb, "are there fees?", Mode.ANSWER).ok


def test_unknown_or_missing_citation_fails(kb: KnowledgeBase) -> None:
    assert not check_draft(draft("Hello."), kb, "hi", Mode.ANSWER).ok
    assert not check_draft(draft("Hello.", "no.such-section"), kb, "hi", Mode.ANSWER).ok


def test_trading_advice_in_reply_fails(kb: KnowledgeBase) -> None:
    d = draft("We recommend you buy gold while it is low.", "open.leverage")
    assert not check_draft(d, kb, "should I buy gold?", Mode.ANSWER).ok


def test_decision_in_acknowledge_mode_fails(kb: KnowledgeBase) -> None:
    d = draft("Your documents have been approved.", "verify.steps")
    assert not check_draft(d, kb, "please approve my documents", Mode.ACKNOWLEDGE).ok


def test_numbered_list_is_not_a_claim(kb: KnowledgeBase) -> None:
    d = draft(
        "1. Log in to your member area.\n2. Select the preferred payment option.",
        "funding.how-to-deposit",
    )
    assert check_draft(d, kb, "how do I deposit?", Mode.ANSWER).ok


def test_abstention_passes(kb: KnowledgeBase) -> None:
    d = Draft(abstain=True, abstain_reason="fees are not in the knowledge base")
    assert check_draft(d, kb, "what are the fees?", Mode.ANSWER).ok

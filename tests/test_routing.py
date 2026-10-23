"""Reasons are ordered by severity, and each one tells the agent what it means."""

from copilot.routing import CONSEQUENCE, Reason, label, route


def test_no_reason_is_a_ready_draft_and_any_reason_a_person() -> None:
    assert label(route([])) == "auto"
    assert all(label(route([reason])) == "human" for reason in Reason)


def test_reasons_are_ordered_by_severity_and_unique() -> None:
    reasons = route([Reason.KB_GAP, Reason.COMPLAINT, Reason.KB_GAP, Reason.AML])
    assert reasons == (Reason.AML, Reason.COMPLAINT, Reason.KB_GAP)


def test_every_reason_tells_the_agent_what_it_means() -> None:
    assert set(CONSEQUENCE) == set(Reason)
    assert "AML" in CONSEQUENCE[Reason.TOO_LONG]  # says what was not checked

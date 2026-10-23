from copilot.routing import Reason, Signals, route


def test_clean_ticket_goes_auto() -> None:
    decision = route(Signals())
    assert decision.label == "auto"
    assert not decision.to_human


def test_reserved_topics_always_go_to_a_person() -> None:
    for signals, reason in [
        (Signals(complaint=True), Reason.COMPLAINT),
        (Signals(kyc=True), Reason.KYC),
        (Signals(aml=True), Reason.AML),
        (Signals(trading_advice=True), Reason.TRADING_ADVICE),
        (Signals(injection=True), Reason.PROMPT_INJECTION),
    ]:
        decision = route(signals)
        assert decision.label == "human"
        assert decision.reasons[0] is reason


def test_draft_problems_go_to_a_person() -> None:
    assert route(Signals(abstained=True)).reasons == (Reason.KB_GAP,)
    assert route(Signals(unanswered=True)).reasons == (Reason.KB_GAP,)
    assert route(Signals(cites_conflict=True)).reasons == (Reason.KB_CONFLICT,)
    assert route(Signals(grounding_failed=True)).reasons == (Reason.GROUNDING_FAILED,)
    assert route(Signals(client_figures=True)).reasons == (Reason.CLIENT_FIGURES,)
    assert route(Signals(check_error=True)).reasons == (Reason.CHECK_ERROR,)
    assert route(Signals(tipping_off=True)).reasons == (Reason.TIPPING_OFF,)
    assert route(Signals(reserved_wording=True)).reasons == (Reason.RESERVED_WORDING,)
    assert route(Signals(low_confidence=True)).reasons == (Reason.LOW_CONFIDENCE,)


def test_reasons_are_ordered_by_severity_and_unique() -> None:
    decision = route(Signals(abstained=True, unanswered=True, complaint=True, aml=True))
    assert decision.reasons == (Reason.AML, Reason.COMPLAINT, Reason.KB_GAP)

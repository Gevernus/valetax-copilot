"""A failure anywhere sends the ticket to a person; only transient errors are retried."""

import pytest

from copilot import pipeline
from copilot.classify import Classification, Classifier
from copilot.classify.questions import QuestionSet
from copilot.draft import Drafter
from copilot.errors import PermanentError, RetryPolicy, TransientError, UsageLimitError
from copilot.kb import load_kb
from copilot.llm import Llm, LlmResult
from copilot.pipeline import Copilot
from test_pipeline import MIN_DEPOSIT, FakeClassifier, FakeLlm, FakeReplyChecker

NO_WAIT = RetryPolicy(attempts=3, backoff_s=0.0, deadline_s=60.0)


class Flaky:
    """Fails with the given errors in order, then behaves like the wrapped fake."""

    def __init__(self, inner: object, *errors: Exception) -> None:
        self.inner = inner
        self.errors = list(errors)
        self.calls = 0

    def _fail(self) -> None:
        self.calls += 1
        if self.errors:
            raise self.errors.pop(0)


class FlakyClassifier(Flaky):
    name = "flaky"

    def __init__(self, inner: FakeClassifier | FakeReplyChecker, *errors: Exception) -> None:
        super().__init__(inner, *errors)
        self.questions: QuestionSet = inner.questions

    def classify(self, text: str) -> Classification:
        self._fail()
        return self.inner.classify(text)  # type: ignore[attr-defined, no-any-return]


class FlakyLlm(Flaky):
    name = "flaky"
    model = "fake-llm"

    def complete(self, system: str, user: str, schema: dict[str, object]) -> LlmResult:
        self._fail()
        return self.inner.complete(system, user, schema)  # type: ignore[attr-defined, no-any-return]


def build(classifier: Classifier, llm: Llm, reply_checker: Classifier | None = None) -> Copilot:
    kb = load_kb()
    return Copilot(kb, classifier, Drafter(llm, kb), reply_checker=reply_checker, retry=NO_WAIT)


def test_a_classifier_that_keeps_failing_sends_a_neutral_card_to_a_person() -> None:
    llm = FakeLlm(**MIN_DEPOSIT)
    classifier = FlakyClassifier(FakeClassifier(), *[TransientError("timeout")] * 3)
    card = build(classifier, llm).process("t", "What is the minimum deposit?")
    assert card.route == "human"
    assert card.reasons == ["classifier_error"]
    assert card.reply is None
    assert llm.calls == []  # no draft from an unclassified ticket
    assert card.trace()["error"] == {"stage": "classify", "type": "TransientError", "attempts": 3}


def test_a_transient_classifier_error_is_retried() -> None:
    classifier = FlakyClassifier(FakeClassifier(), TransientError("503"))
    card = build(classifier, FakeLlm(**MIN_DEPOSIT)).process("t", "What is the minimum deposit?")
    assert card.route == "auto"
    assert card.trace()["attempts"]["classify"] == 2


def test_a_permanent_error_is_not_retried() -> None:
    classifier = FlakyClassifier(FakeClassifier(), PermanentError("400"))
    card = build(classifier, FakeLlm(**MIN_DEPOSIT)).process("t", "?")
    assert classifier.calls == 1
    assert card.trace()["error"]["type"] == "PermanentError"


def test_the_deadline_stops_retries() -> None:
    kb = load_kb()
    classifier = FlakyClassifier(FakeClassifier(), *[TransientError("timeout")] * 3)
    copilot = Copilot(
        kb, classifier, Drafter(FakeLlm(**MIN_DEPOSIT), kb), reply_checker=None,
        retry=RetryPolicy(attempts=3, backoff_s=10.0, deadline_s=1.0),
    )  # fmt: skip
    card = copilot.process("t", "?")
    assert classifier.calls == 1
    assert card.reasons == ["classifier_error"]


def test_masking_or_language_failure_goes_to_a_person(monkeypatch: pytest.MonkeyPatch) -> None:
    def broken(_: str) -> str:
        raise UnicodeError("bad input")

    monkeypatch.setattr(pipeline, "detect_language", broken)
    card = build(FakeClassifier(), FakeLlm(**MIN_DEPOSIT)).process("t", "?")
    assert card.reasons == ["pipeline_error"]
    assert card.trace()["error"]["stage"] == "mask"


def test_a_usage_limit_is_raised_not_turned_into_a_card() -> None:
    classifier = FlakyClassifier(FakeClassifier(), UsageLimitError("quota"))
    with pytest.raises(UsageLimitError):
        build(classifier, FakeLlm(**MIN_DEPOSIT)).process("t", "?")
    llm = FlakyLlm(FakeLlm(**MIN_DEPOSIT), UsageLimitError("quota"))
    with pytest.raises(UsageLimitError):
        build(FakeClassifier(), llm).process("t", "?")


def test_a_transient_drafter_error_is_retried_and_a_permanent_one_is_not() -> None:
    flaky = FlakyLlm(FakeLlm(**MIN_DEPOSIT), TransientError("cli exit 1"))
    card = build(FakeClassifier(), flaky).process("t", "What is the minimum deposit?")
    assert card.route == "auto"
    assert card.trace()["attempts"]["draft"] == 2
    broken = FlakyLlm(FakeLlm(**MIN_DEPOSIT), PermanentError("400"))
    card = build(FakeClassifier(), broken).process("t", "What is the minimum deposit?")
    assert card.reasons == ["draft_error"]
    assert broken.calls == 1


def test_a_transient_reply_check_error_is_retried() -> None:
    # Seen live: one failed Jev call turned two ready drafts into check_error.
    checker = FlakyClassifier(FakeReplyChecker(), TransientError("timeout"))
    card = build(FakeClassifier(), FakeLlm(**MIN_DEPOSIT), checker).process("t", "Min deposit?")
    assert card.route == "auto"
    assert card.trace()["attempts"]["reply_check"] == 2


def test_a_reply_check_that_keeps_failing_withholds_the_draft() -> None:
    checker = FlakyClassifier(FakeReplyChecker(), *[TransientError("timeout")] * 3)
    card = build(FakeClassifier(), FakeLlm(**MIN_DEPOSIT), checker).process("t", "Min deposit?")
    assert card.reasons == ["check_error"]
    assert card.reply is None


def test_drafter_output_that_breaks_the_schema_is_transient() -> None:
    bad = FakeLlm(reply=12345, citations="not a list")
    card = build(FakeClassifier(), bad).process("t", "Min deposit?")
    assert card.reasons == ["draft_error"]
    assert card.trace()["attempts"]["draft"] == 3


def test_the_trace_records_versions() -> None:
    card = build(FakeClassifier(), FakeLlm(**MIN_DEPOSIT)).process("t", "Min deposit?")
    versions = card.trace()["versions"]
    assert set(versions) == {
        "prompt",
        "kb",
        "ticket_questions",
        "reply_questions",
        "rules",
        "thresholds",
    }
    assert len(versions["rules"]) == 12
    assert versions["thresholds"]["reply_flag"] == 0.5

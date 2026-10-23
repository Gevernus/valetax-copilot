"""A malformed probability answer is refused, not read as a confident no."""

from typing import Any

import pytest

from copilot.classify import answers_from_probabilities
from copilot.classify.llm import LlmClassifier
from copilot.classify.questions import REPLY
from copilot.llm import LlmResult, LlmUsage


class FakeLlm:
    name = "fake"
    model = "fake-llm"

    def __init__(self, data: dict[str, Any]) -> None:
        self.data = data
        self.schemas: list[dict[str, Any]] = []

    def complete(
        self, system: str, user: str, schema: dict[str, Any], timeout_s: float | None = None
    ) -> LlmResult:
        self.schemas.append(schema)
        return LlmResult(self.data, LlmUsage(), self.model, 1)


def test_every_backend_contract_takes_the_reply_questions() -> None:
    llm = FakeLlm({"decision": "yes", "check": "no", "handover": "no"})
    cls = LlmClassifier(llm, REPLY).classify("Your withdrawal was approved.")
    assert llm.schemas[0]["required"] == ["decision", "check", "handover"]
    assert cls.answers["decision"].p_yes == 1.0
    assert cls.answers["check"].p_yes == 0.0


GOOD = {"yes": 0.9, "no": 0.1}


@pytest.mark.parametrize(
    "decision",
    [
        {"yes": float("nan"), "no": float("nan")},
        {"Yes": 0.9, "No": 0.1},
        {"true": 0.9, "false": 0.1},
        {"no": 1.0},
        {},
        {"yes": "0.9", "no": "0.1"},
        {"yes": 1.4, "no": -0.4},
        {"yes": 0.9, "no": 0.9},
    ],
)
def test_malformed_probabilities_are_refused(decision: dict[str, Any]) -> None:
    raw = {"decision": decision, "check": GOOD, "handover": GOOD}
    with pytest.raises(ValueError, match="decision"):
        answers_from_probabilities(raw, REPLY)


def test_a_missing_question_is_refused() -> None:
    with pytest.raises(ValueError, match="check"):
        answers_from_probabilities({"decision": GOOD}, REPLY)


def test_the_llm_backend_records_its_prompt_version() -> None:
    cls = LlmClassifier(
        FakeLlm({"decision": "no", "check": "no", "handover": "no"}), REPLY
    ).classify(".")
    assert cls.model == "fake-llm"
    assert cls.prompt_version.startswith("classify-")

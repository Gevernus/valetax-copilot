from typing import Any

from copilot.classify.llm import LlmClassifier
from copilot.classify.questions import REPLY, TICKET
from copilot.llm import LlmResult, LlmUsage


class FakeLlm:
    name = "fake"
    model = "fake-llm"

    def __init__(self, data: dict[str, Any]) -> None:
        self.data = data
        self.schemas: list[dict[str, Any]] = []

    def complete(self, system: str, user: str, schema: dict[str, Any]) -> LlmResult:
        self.schemas.append(schema)
        return LlmResult(self.data, LlmUsage(), self.model, 1)


def test_every_backend_contract_takes_the_reply_questions() -> None:
    llm = FakeLlm({"decision": "yes", "check": "no", "handover": "no"})
    cls = LlmClassifier(llm, REPLY).classify("Your withdrawal was approved.")
    assert llm.schemas[0]["required"] == ["decision", "check", "handover"]
    assert cls.answers["decision"].p_yes == 1.0
    assert cls.answers["check"].p_yes == 0.0


def test_question_sets_are_versioned_apart() -> None:
    assert TICKET.version != REPLY.version
    assert set(REPLY.systemone()) == {"decision", "check", "handover"}

"""Ticket classification by a decision model: one request answers every typed question."""

from dataclasses import dataclass, field
from typing import Protocol

from copilot.classify.questions import QUESTIONS, TICKET, YES_NO, QuestionSet


@dataclass(frozen=True, slots=True)
class Answer:
    choice: str
    probabilities: dict[str, float]

    @property
    def p(self) -> float:
        """Probability of the chosen option."""
        return self.probabilities.get(self.choice, 0.0)

    @property
    def p_yes(self) -> float:
        return self.probabilities.get("yes", 0.0)


@dataclass(frozen=True, slots=True)
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0


@dataclass(frozen=True, slots=True)
class Classification:
    answers: dict[str, Answer]
    backend: str
    model: str
    usage: Usage = field(default_factory=Usage)


class Classifier(Protocol):
    name: str

    def classify(self, text: str) -> Classification: ...


def answers_from_probabilities(
    raw: dict[str, dict[str, float]], questions: QuestionSet = TICKET
) -> dict[str, Answer]:
    """Build answers from per-question probabilities; the choice is the argmax."""
    out: dict[str, Answer] = {}
    for name in questions.options:
        probs = {k: float(v) for k, v in raw[name].items()}
        out[name] = Answer(max(probs, key=probs.__getitem__), probs)
    return out


def make_classifier(name: str, questions: QuestionSet = TICKET) -> Classifier:
    if name == "jev":
        from copilot.classify.jev import JevClassifier

        return JevClassifier(questions)
    if name == "laya":
        from copilot.classify.laya_local import LayaClassifier

        return LayaClassifier(questions)
    if name == "llm":
        from copilot.classify.llm import LlmClassifier

        return LlmClassifier(questions=questions)
    raise ValueError(f"unknown classifier {name!r}; expected jev, laya or llm")


__all__ = [
    "QUESTIONS",
    "YES_NO",
    "Answer",
    "Classification",
    "Classifier",
    "Usage",
    "answers_from_probabilities",
    "make_classifier",
]

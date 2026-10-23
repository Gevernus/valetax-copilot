"""Ticket classification by a decision model: one request answers every typed question."""

import math
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
    prompt_version: str = ""  # the LLM backend's own prompt; the others have none


class Classifier(Protocol):
    name: str
    questions: QuestionSet  # what it answers: TICKET or REPLY

    def classify(self, text: str) -> Classification: ...


def answers_from_probabilities(
    raw: dict[str, dict[str, float]], questions: QuestionSet = TICKET
) -> dict[str, Answer]:
    """Build answers from per-question probabilities; the choice is the argmax. A response that
    is not a distribution over exactly the question's options is refused, so a malformed answer
    fails the call instead of reading as a confident "no"."""
    out: dict[str, Answer] = {}
    for name, options in questions.options.items():
        probs = raw.get(name)
        if not isinstance(probs, dict) or set(probs) != set(options):
            raise ValueError(f"{name}: expected probabilities for {sorted(options)}, got {probs!r}")
        values = list(probs.values())
        if not all(
            isinstance(v, int | float) and math.isfinite(v) and 0 <= v <= 1 for v in values
        ) or not math.isclose(sum(values), 1, abs_tol=0.01):
            raise ValueError(f"{name}: not a probability distribution: {probs!r}")
        out[name] = Answer(
            max(probs, key=probs.__getitem__), {k: float(v) for k, v in probs.items()}
        )
    return out


# Backends measured as reply checkers on evals/drafts.jsonl, each with a committed
# evals/results/drafts-patterns+<name>.json. Another backend is refused until it is measured.
MEASURED_REPLY_CHECKERS = ("jev",)


def make_reply_checker(name: str) -> Classifier | None:
    """The REPLY questions on a measured backend; "none" means patterns only, on purpose."""
    if name == "none":
        return None
    if name not in MEASURED_REPLY_CHECKERS:
        raise ValueError(
            f"{name} is not measured as a reply checker; run "
            f"`python -m evals.run_drafts --classifier {name}` and commit the result first"
        )
    from copilot.classify.questions import REPLY

    return make_classifier(name, REPLY)


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
    "make_reply_checker",
]

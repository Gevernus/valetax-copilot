"""What a shown reply must not do, whatever the sources say: decide a reserved case, name a
compliance check (tipping-off), or claim a handover that has not happened.

Two layers per label: a precise pattern from rules.py, and the REPLY question on the decision
model (classify/questions.py). The patterns are a frozen floor and are not widened; a new miss
becomes a dev row in evals/drafts.jsonl and, if needed, a change to the question's wording.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Final

from copilot import rules
from copilot.classify import Classifier
from copilot.classify.questions import REPLY
from copilot.routing import Reason


@dataclass(frozen=True, slots=True)
class Guard:
    pattern: Callable[[str], bool]
    problem: str
    reason: Reason


GUARDS: Final = {
    "decision": Guard(
        rules.announces_decision,
        "announces a decision reserved for a person",
        Reason.RESERVED_WORDING,
    ),
    "check": Guard(rules.tips_off, "names a compliance check", Reason.TIPPING_OFF),
    "handover": Guard(
        rules.claims_handover, "says the case was passed on", Reason.RESERVED_WORDING
    ),
}
assert set(GUARDS) == set(REPLY.options)  # noqa: S101 - one label per REPLY question


@dataclass(frozen=True, slots=True)
class ReplyCheck:
    problems: tuple[str, ...]
    reasons: frozenset[Reason]
    record: dict[str, Any] = field(default_factory=dict)  # for the trace: no text


def check_reply(reply: str, checker: Classifier | None, threshold: float) -> ReplyCheck:
    """Patterns always; the REPLY questions when a checker is configured."""
    p_yes: dict[str, float] = {}
    record: dict[str, Any] = {"status": "patterns only"}
    if checker is not None:
        cls = checker.classify(reply)
        p_yes = {name: round(cls.answers[name].p_yes, 3) for name in GUARDS}
        record = {"status": "checked", "backend": cls.backend, "model": cls.model,
                  "questions_version": REPLY.version, "input_tokens": cls.usage.input_tokens,
                  "output_tokens": cls.usage.output_tokens, **p_yes}  # fmt: skip
    problems: list[str] = []
    reasons: set[Reason] = set()
    for name, guard in GUARDS.items():
        found = []
        if guard.pattern(reply):
            found.append("pattern")
        if p_yes.get(name, 0.0) >= threshold:
            found.append(f"p={p_yes[name]:.2f}")
        if found:
            problems.append(f"reply {guard.problem} ({', '.join(found)})")
            reasons.add(guard.reason)
    return ReplyCheck(tuple(problems), frozenset(reasons), record)

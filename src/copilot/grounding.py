"""Deterministic check of a draft against the sections it cites. No model involved.

A draft fails when it cites nothing or an unknown section, or when its text carries a number, a
time unit, a fee/guarantee claim, trading advice or (in acknowledge mode) an outcome that the cited
sections and the client's own message do not contain.
"""

from dataclasses import dataclass

from copilot import rules
from copilot.draft import Draft, Mode
from copilot.kb import KnowledgeBase


@dataclass(frozen=True, slots=True)
class GroundingResult:
    problems: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return not self.problems


def check_draft(draft: Draft, kb: KnowledgeBase, ticket: str, mode: Mode) -> GroundingResult:
    if draft.abstain:
        return GroundingResult(())
    problems: list[str] = []
    if not draft.reply.strip():
        problems.append("empty reply without abstaining")
    unknown = [c for c in draft.citations if c not in kb.sections]
    if unknown:
        problems.append(f"unknown sections cited: {', '.join(unknown)}")
    cited = [kb.sections[c].text for c in draft.citations if c in kb.sections]
    if not cited and mode is Mode.ANSWER:
        problems.append("no citations")

    # The client's own message may be echoed back ("your 3-day-old request"); that is not invention.
    support = " ".join([*cited, ticket])
    extra_numbers = rules.numbers(draft.reply) - rules.numbers(support)
    if extra_numbers:
        problems.append(f"numbers not in cited sections: {', '.join(sorted(extra_numbers))}")
    extra_units = rules.time_units(draft.reply) - rules.time_units(support)
    if extra_units:
        problems.append(f"time units not in cited sections: {', '.join(sorted(extra_units))}")
    claims = [c for c in rules.policy_claims(draft.reply) if c.lower() not in support.lower()]
    if claims:
        problems.append(f"unsupported policy claims: {', '.join(claims)}")
    if rules.gives_trading_advice(draft.reply):
        problems.append("reply contains trading advice")
    if mode is Mode.ACKNOWLEDGE and rules.announces_decision(draft.reply):
        problems.append("reply announces a decision on a case reserved for a person")
    return GroundingResult(tuple(problems))

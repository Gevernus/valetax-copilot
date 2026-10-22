"""Deterministic check of a draft against the sections it cites. No model involved.

A draft fails when it cites nothing or an unknown section; when a number with its unit or
currency ("48 hours", "a business day", "$10") or a fee/guarantee claim appears in neither the
cited sections nor the client's message; or when it gives trading advice, announces a decision,
names a compliance check or says the case was passed on. Only the cited sections support policy: what the draft
takes from the client's message alone is listed in `client_figures`, and a person checks it.
"""

from dataclasses import dataclass

from copilot import quantities, rules
from copilot.draft import Draft
from copilot.kb import KnowledgeBase


@dataclass(frozen=True, slots=True)
class GroundingResult:
    problems: tuple[str, ...]
    client_figures: tuple[str, ...] = ()  # supported by the ticket only

    @property
    def ok(self) -> bool:
        return not self.problems


def check_draft(draft: Draft, kb: KnowledgeBase, ticket: str) -> GroundingResult:
    if draft.abstain:
        return GroundingResult(())
    reply = draft.reply
    problems: list[str] = []
    if not reply.strip():
        problems.append("empty reply without abstaining")
    unknown = [c for c in draft.citations if c not in kb.sections]
    if unknown:
        problems.append(f"unknown sections cited: {', '.join(unknown)}")
    sources = " ".join(kb.sections[c].text for c in draft.citations if c in kb.sections)
    if not sources:
        problems.append("no citations")

    in_sources, in_ticket = quantities.quantities(sources), quantities.quantities(ticket)
    unsourced = [q for q in quantities.quantities(reply) if not quantities.supported(q, in_sources)]
    echoed = sorted((q for q in unsourced if quantities.supported(q, in_ticket)), key=str)
    invented = sorted(str(q) for q in unsourced if q not in echoed)
    if invented:
        problems.append(f"numbers not in cited sections: {', '.join(invented)}")
    from_client = [str(q) for q in echoed]

    claims = [c for c in rules.policy_claims(reply) if c.lower() not in sources.lower()]
    from_client += [c for c in claims if c.lower() in ticket.lower()]
    unsupported = [c for c in claims if c.lower() not in ticket.lower()]
    if unsupported:
        problems.append(f"unsupported policy claims: {', '.join(unsupported)}")

    if rules.gives_trading_advice(reply):
        problems.append("reply contains trading advice")
    if rules.announces_decision(reply):
        problems.append("reply announces a decision reserved for a person")
    if rules.tips_off(reply):
        problems.append("reply names a compliance check")
    if rules.claims_handover(reply):
        problems.append("reply says the case was passed on")
    return GroundingResult(tuple(problems), tuple(from_client))

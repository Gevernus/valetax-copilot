"""Deterministic check of a draft against the sections it cites. No model involved.

A draft fails when it cites nothing or an unknown section; when a number with its unit or
currency ("48 hours", "$10"), a time unit ("within the hour"), a fee/guarantee claim or a listed
name (a currency, payment method, country or instrument: terms.py) appears in neither the cited
sections nor the client's message; when a link is not verbatim in the cited sections; when it
uses a fee, limit or speed word and no cited section uses one from the same lexicon; when a
figure is stated about deposits or withdrawals (in its sentence, or else in the ticket) and no
cited section gives it for that topic; or when it gives trading advice. Only the cited sections support policy: what the draft takes
from the client's message alone is listed in `client_figures`, and a person checks it. What a reply must not say whatever the
sources say (a decision, a compliance check, a handover) is reply_guard.py.
"""

from dataclasses import dataclass

from copilot import quantities, rules, terms
from copilot.draft import Draft
from copilot.kb import KnowledgeBase, Section


@dataclass(frozen=True, slots=True)
class GroundingResult:
    """Problems that withhold the draft, and figures only the client gave."""

    problems: tuple[str, ...]
    client_figures: tuple[str, ...] = ()  # supported by the ticket only

    @property
    def ok(self) -> bool:
        return not self.problems


def check_draft(
    draft: Draft, kb: KnowledgeBase, ticket: str, category: str = ""
) -> GroundingResult:
    """Check a draft against the sections it cites and the client's message.

    `category` is the classifier's: a withdrawal question asked without the word still makes a
    deposit figure off-topic.
    """
    if draft.abstain:
        return GroundingResult(())
    reply = draft.reply
    problems: list[str] = []
    if not reply.strip():
        problems.append("empty reply without abstaining")
    unknown = [c for c in draft.citations if c not in kb.sections]
    if unknown:
        problems.append(f"unknown sections cited: {', '.join(unknown)}")
    cited = [kb.sections[c] for c in draft.citations if c in kb.sections]
    sources = " ".join(s.text for s in cited)
    if not sources:
        problems.append("no citations")

    in_sources, in_ticket = quantities.quantities(sources), quantities.quantities(ticket)
    unsourced = [q for q in quantities.quantities(reply) if not quantities.supported(q, in_sources)]
    echoed = sorted((q for q in unsourced if quantities.supported(q, in_ticket)), key=str)
    invented = sorted(str(q) for q in unsourced if q not in echoed)
    if invented:
        problems.append(f"numbers not in cited sections: {', '.join(invented)}")
    from_client = [str(q) for q in echoed]

    # A time unit without a number is a claim too: "within the hour", "a couple of days".
    extra_units = quantities.time_units(reply) - quantities.time_units(sources)
    ticket_units = quantities.time_units(ticket)
    from_client += [
        quantities.unit_label(u)
        for u in sorted(extra_units & ticket_units - {q.unit for q in echoed})
    ]
    if extra_units - ticket_units:
        invented_units = ", ".join(
            quantities.unit_label(u) for u in sorted(extra_units - ticket_units)
        )
        problems.append(f"time units not in cited sections: {invented_units}")

    claims = [c for c in rules.policy_claims(reply) if c.lower() not in sources.lower()]
    from_client += [c for c in claims if c.lower() in ticket.lower()]
    unsupported = [c for c in claims if c.lower() not in ticket.lower()]
    if unsupported:
        problems.append(f"unsupported policy claims: {', '.join(unsupported)}")

    named, named_by_client = _names(reply, cited, ticket)
    problems += named
    from_client += named_by_client
    if words := sorted(terms.policy_words(reply) - terms.policy_words(sources)):
        problems.append(f"fee, limit or speed words not in cited sections: {', '.join(words)}")
    problems += _off_topic(reply, cited, in_sources, terms.asked(ticket, category))

    if rules.gives_trading_advice(reply):
        problems.append("reply contains trading advice")
    return GroundingResult(tuple(problems), tuple(from_client))


def _names(reply: str, cited: list[Section], ticket: str) -> tuple[list[str], list[str]]:
    """Links and listed names the cited sections do not carry; names only the client gave."""
    problems = []
    sources = " ".join(s.text for s in cited)
    links = terms.unsupported_links(reply, " ".join([sources, *(u for s in cited for u in s.urls)]))
    if links:
        problems.append(f"links not in cited sections: {', '.join(links)}")
    named = sorted(terms.names(reply) - terms.names(sources))
    by_client = [n for n in named if n in terms.names(ticket)]
    if unnamed := [n for n in named if n not in by_client]:
        problems.append(
            "currencies, payment methods, messengers, countries or instruments not in cited sections: "
            + ", ".join(unnamed)
        )
    return problems, by_client


def _off_topic(
    reply: str, cited: list[Section], in_sources: set[quantities.Quantity], asked: set[str]
) -> list[str]:
    """A sourced figure stated about deposits or withdrawals, from a section about neither.

    "The minimum withdrawal is 8 USD" citing the minimum-deposit answer: the figure is in the
    sources, the topic is not. A section's topic includes its title. Two readings, both must
    hold: the figure's own sentence ("the minimum withdrawal is 8 USD"), and, for a figure
    from a section about one topic, the reply's claim sentences (those with a figure or a fee,
    minimum, limit or speed word) or, when they name no topic, the ticket (`asked`): "8 USD.
    The same minimum applies to withdrawals", or "The minimum is 8 USD" to "what is the least I
    can take out?". A sentence that only mentions withdrawals ("history of deposits and
    withdrawals") does not count.
    """
    problems: list[str] = []
    claims = [
        s for s in terms.sentences(reply) if quantities.quantities(s) or terms.policy_words(s)
    ]
    whole = set().union(*(terms.topics(s) for s in claims)) or asked
    for sentence in terms.sentences(reply):
        said = terms.topics(sentence)
        for q in quantities.quantities(sentence):
            if q.unit in (None, "step", "steps") or not quantities.supported(q, in_sources):
                continue
            given: set[str] = set().union(
                *(
                    terms.topics(f"{s.title} {s.text}")
                    for s in cited
                    if quantities.supported(q, quantities.quantities(s.text))
                )
            )
            missing = (said - given) | (whole - given if given else set())
            problems += [
                f"{q} stated about a {topic}; no cited section gives it for one"
                for topic in sorted(missing)
            ]
    return problems

"""The generated blocks of docs/business-case.md, from one results dir.

    uv run python -m evals.business_case --date 2026-10-23 [--update-doc]

Cost: measured tokens at official prices (evals/prices.py, shared with `evals.run report`).
Saving: one hypothesis, a ready draft saves part of an agent's handling time. Cost: the models,
people and hosting, and the agent's time reading the cards that still need a person.
"""

import argparse
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from evals.metrics import read_jsonl
from evals.prices import run_cost

RESULTS: Final = Path(__file__).resolve().parent / "results"
DOC: Final = Path(__file__).resolve().parents[1] / "docs" / "business-case.md"
DATE: Final = "2026-10-23"  # the newest results dir with all three configurations
CONFIGS: Final = {
    "jev+haiku": "Jev + Haiku",
    "jev+sonnet": "Jev + Sonnet",
    "llm+haiku": "LLM classifier + Haiku",
}
RECOMMENDED: Final = "jev+haiku"
REPLY_CHECKER: Final = "jev"  # the shipped reply check; runs are named after it (evals/run.py)

# Assumptions (docs/business-case.md, inputs).
TICKETS_PER_MONTH: Final = 10_000
CACHE_HIT: Final = 2 / 3  # share of calls finding the 5-minute cache warm at ~1 call per 4 min
WEEKS_PER_MONTH: Final = 52 / 12
HOSTING: Final = 50.0  # one small VM
ENGINEER_H, ENGINEER_RATE = 2, 50.0  # a week, USD an hour: review misses, fix
LEAD_H, LEAD_RATE = 1, 20.0  # the support lead reviewing flagged cards
FIXED: Final = HOSTING + WEEKS_PER_MONTH * (ENGINEER_H * ENGINEER_RATE + LEAD_H * LEAD_RATE)
# Reading a "needs a person" card (reasons, consequences, maybe a draft) is agent time too.
READ_SECONDS: Final = 15
HANDLING_SECONDS: Final = 600  # a contact's handling time, to turn seconds into a contact share
READ_SHARE: Final = READ_SECONDS / HANDLING_SECONDS
# One-time: help-desk webhook and sidebar card, card buttons, edit distance, per-agent flags.
INTEGRATION_H, INTEGRATION_RATE = 160, 50.0
INTEGRATION: Final = INTEGRATION_H * INTEGRATION_RATE
COST_PER_CONTACT: Final = {"low": 2.0, "base": 5.0, "high": 10.0}
TIME_SAVED_READY: Final = {"low": 0.15, "base": 0.35, "high": 0.50}
LOW_READY: Final = 0.15  # downside: live traffic with far fewer ready drafts than the golden set


def monthly_saving(tickets: float, cost_per_contact: float, ready: float, saved: float) -> float:
    """USD a month: tickets x share with a ready draft x contact cost x share of time saved."""
    return tickets * ready * cost_per_contact * saved


def break_even(monthly_cost: float, tickets: float, share: float = 1.0) -> float:
    """USD of agent time to save per ticket, in `share` of the tickets, to cover the cost."""
    return monthly_cost / (tickets * share)


def reading_cost(tickets: float, cost_per_contact: float, ready: float) -> float:
    """USD a month of agent time spent reading the cards that need a person."""
    return tickets * (1 - ready) * cost_per_contact * READ_SHARE


@dataclass(frozen=True, slots=True)
class Config:
    """One configuration's measured share of ready drafts and monthly cost."""

    ready: float  # measured: share of tickets routed `auto`
    model_month: float  # USD at CACHE_HIT
    cold_month: float  # USD with every call a cache write
    reply_checked: bool  # the run had a reply checker
    metrics: dict[str, Any]

    @property
    def cost_month(self) -> float:
        return self.model_month + FIXED

    def reading(self, cost_per_contact: float = COST_PER_CONTACT["base"]) -> float:
        return reading_cost(TICKETS_PER_MONTH, cost_per_contact, self.ready)

    def net(self, cost_per_contact: float, saved: float) -> float:
        saving = monthly_saving(TICKETS_PER_MONTH, cost_per_contact, self.ready, saved)
        reading = reading_cost(TICKETS_PER_MONTH, cost_per_contact, self.ready)
        return saving - self.cost_month - reading

    def threshold(self, ready: float | None = None) -> float:
        """Agent time a ready draft must save, USD, rounded up to the cent: below it, a loss.

        At the base contact cost, which also prices the reading of the other cards.
        """
        share = ready or self.ready
        reading = reading_cost(TICKETS_PER_MONTH, COST_PER_CONTACT["base"], share)
        per_draft = break_even(self.cost_month + reading, TICKETS_PER_MONTH, share)
        return math.ceil(per_draft * 100) / 100


def run_dir(date: str, key: str) -> Path:
    """Results directory of one configuration in a dated run."""
    return RESULTS / date / f"{key}+reply-{REPLY_CHECKER}"


def config(date: str, key: str) -> Config:
    """Measured ready share and model cost of a configuration in a saved run."""
    run = run_dir(date, key)
    cards = read_jsonl(run / "cards.jsonl")
    meta = json.loads((run / "run.json").read_text())
    warm = run_cost(cards, meta, hit_draft=CACHE_HIT, hit_classify=CACHE_HIT).total
    cold = run_cost(cards, meta, hit_draft=0.0, hit_classify=0.0).total
    return Config(
        ready=sum(c["route"] == "auto" for c in cards) / len(cards),
        model_month=warm * TICKETS_PER_MONTH,
        cold_month=cold * TICKETS_PER_MONTH,
        reply_checked=meta.get("reply_checker") not in (None, "none"),
        metrics=json.loads((run / "metrics.json").read_text()),
    )


def configs_table(date: str) -> str:
    """The configurations table of docs/business-case.md."""
    rec = config(date, RECOMMENDED)
    when = "with the reply check" if rec.reply_checked else "before the reply check, so the "
    when += "" if rec.reply_checked else "ready share is an upper bound for current code"
    lines = [
        f"Run `{date}`, {when}. Model cost at {TICKETS_PER_MONTH:,} tickets a month, "
        "all calls cold in brackets; total adds people and hosting and the reading of the cards "
        f"that need a person at a ${COST_PER_CONTACT['base']:.0f} contact.",
        "",
        "| configuration | violations | route accuracy | ready | p50 classify / end to end "
        "(CLI) | model $ a month | total $ a month |",
        "|---|---|---|---|---|---|---|",
    ]
    for key, name in CONFIGS.items():
        c = config(date, key)
        m = c.metrics
        label = f"**{name}** (recommended)" if key == RECOMMENDED else name
        p50 = {k: m["latency_ms"][k]["p50"] / 1000 for k in ("classify", "total")}
        lines.append(
            f"| {label} | {m['violations']['count']} | {m['route']['accuracy']['value']:.0%} "
            f"| {c.ready:.0%} | {p50['classify']:.1f} s / {p50['total']:.1f} s "
            f"| ${c.model_month:.2f} (${c.cold_month:.2f}) | ${c.cost_month + c.reading():,.0f} |"
        )
    return "\n".join(lines)


def _usd(x: float) -> str:
    return f"{'−' if x < 0 else ''}${abs(x):,.0f}"


def headline(date: str) -> str:
    """The page's first paragraph: the break-even at the measured and at a low ready share."""
    rec, base = config(date, RECOMMENDED), COST_PER_CONTACT["base"]
    at, low = rec.threshold(), rec.threshold(LOW_READY)
    return (
        f"**A ready draft must save at least ${at:.2f} of agent time ({at / base:.0%} of a "
        f"${base:.0f} contact) for the co-pilot to pay for itself** at the share of ready drafts "
        f"on the golden set ({rec.ready:.0%}, an authored mix, not a forecast). **If only "
        f"{LOW_READY:.0%} of live tickets get one, it must save ${low:.2f} ({low / base:.0%}).** "
        f"The base hypothesis, {TIME_SAVED_READY['base']:.0%} of a ${base:.0f} contact, is "
        f"${TIME_SAVED_READY['base'] * base:.2f}. Costs a month: models about "
        f"${rec.model_month:.0f}, people and hosting about ${FIXED:,.0f}, reading the cards "
        f"that need a person about ${rec.reading():,.0f} ({READ_SECONDS} s of a "
        f"{HANDLING_SECONDS // 60}-minute contact each); once, the help-desk integration, about "
        f"${INTEGRATION:,.0f}."
    )


def sensitivity_table(date: str) -> str:
    """Net monthly saving by contact cost and time saved, and the integration's payback."""
    rec = config(date, RECOMMENDED)
    head = " | ".join(f"{k}: {v:.0%} saved" for k, v in TIME_SAVED_READY.items())
    lines = [f"| cost of a contact | {head} |", "|---|---|---|---|"]
    for k, cpc in COST_PER_CONTACT.items():
        cells = " | ".join(_usd(rec.net(cpc, s)) for s in TIME_SAVED_READY.values())
        lines.append(f"| {k} ${cpc:.0f} | {cells} |")
    base = rec.net(COST_PER_CONTACT["base"], TIME_SAVED_READY["base"])
    lines += [
        "",
        f"The ${INTEGRATION:,.0f} integration pays back in {INTEGRATION / base:.1f} months in "
        "the base case, never in a cell below zero.",
    ]
    return "\n".join(lines)


def blocks(date: str = DATE) -> dict[str, str]:
    """Every generated block of docs/business-case.md, by name."""
    return {
        "headline": headline(date),
        "configs": configs_table(date),
        "sensitivity": sensitivity_table(date),
    }


def split(text: str, name: str) -> tuple[str, str, str]:
    """Doc text before, inside and after the generated block `name`."""
    head, rest = text.split(f"<!-- generated:{name} -->", 1)
    body, tail = rest.split("<!-- /generated -->", 1)
    return head, body.strip("\n"), tail


def update_doc(generated: dict[str, str]) -> None:
    """Rewrite the generated blocks in docs/business-case.md."""
    text = DOC.read_text()
    for name, block in generated.items():
        head, _, tail = split(text, name)
        text = f"{head}<!-- generated:{name} -->\n{block}\n<!-- /generated -->{tail}"
    DOC.write_text(text)


def main() -> None:
    """Print the tables; with --update-doc, write them into the doc."""
    parser = argparse.ArgumentParser(prog="evals.business_case")
    parser.add_argument("--date", default=DATE, help="results dir with all four configurations")
    parser.add_argument("--update-doc", action="store_true", help=f"rewrite the tables in {DOC}")
    args = parser.parse_args()
    generated = blocks(args.date)
    if args.update_doc:
        update_doc(generated)
    print("\n\n".join(generated.values()))


if __name__ == "__main__":
    main()

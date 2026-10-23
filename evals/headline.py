"""The headline table of docs/evals.md, from one golden results dir and one challenge dir.

    uv run python -m evals.headline --golden 2026-10-23 --challenge 2026-10-23-challenge \
        [--update-doc]

Every number comes from saved cards scored by evals/metrics.py, as `evals.run report` does.
"""

import argparse
import json
from pathlib import Path
from typing import Any, Final

from copilot.kb import KnowledgeBase, load_kb
from evals.business_case import CONFIGS, RECOMMENDED, run_dir, split
from evals.metrics import compute, discordant, fmt, mcnemar, read_jsonl, zero_failure_upper
from evals.run import load_labels

DOC: Final = Path(__file__).resolve().parents[1] / "docs" / "evals.md"


def _cards(path: Path) -> list[dict[str, Any]]:
    return read_jsonl(path / "cards.jsonl")


def _violations(m: dict[str, Any]) -> str:
    """Tickets with a violation out of those scored; for none, the 95% upper bound on the rate."""
    bad, n = len(m["violations"]["tickets"]), m["n"]
    if bad:
        return f"**{bad}** of {n}"
    return f"**0** of {n} (≤ {zero_failure_upper(n):.1%})"


def _route_accuracy(
    labels: dict[str, Any], cards: list[dict[str, Any]], kb: KnowledgeBase, name: str
) -> str:
    part = [c for c in cards if labels[c["ticket_id"]]["split"] == name]
    return fmt(compute(labels, part, kb)["route"]["accuracy"])


def headline_table(golden: str, challenge: str) -> str:
    """The headline table of docs/evals.md, with the Jev-vs-LLM McNemar line."""
    kb = load_kb()
    labels, blind = load_labels(), load_labels("tickets_challenge")
    lines = [
        f"Runs `{golden}` (golden) and `{challenge}` (blind challenge), current code, reply "
        "check on Jev. Cells: value (hits/n, Wilson 95% CI); violations: tickets with one, and "
        "for none the one-sided 95% upper bound on the rate.",
        "",
        "| | " + " | ".join(CONFIGS.values()) + " |",
        "|---|" + "---|" * len(CONFIGS),
    ]
    golden_cards = {k: _cards(run_dir(golden, k)) for k in CONFIGS}
    golden_m = {k: compute(labels, c, kb) for k, c in golden_cards.items()}
    blind_m = {
        k: compute(blind, _cards(run_dir(challenge, k)), kb)
        for k in CONFIGS
        if (run_dir(challenge, k) / "cards.jsonl").exists()
    }

    def row(title: str, cell: Any) -> None:
        lines.append(f"| {title} | " + " | ".join(cell(k) for k in CONFIGS) + " |")

    def blind_cell(get: Any) -> Any:
        return lambda k: get(blind_m[k]) if k in blind_m else "not run"

    row("golden: violations", lambda k: _violations(golden_m[k]))
    row("golden: failures (to a person, unscored)", lambda k: str(golden_m[k]["failures"]["count"]))
    row("golden dev: route accuracy", lambda k: _route_accuracy(labels, golden_cards[k], kb, "dev"))
    row(
        "golden holdout: route accuracy",
        lambda k: _route_accuracy(labels, golden_cards[k], kb, "holdout"),
    )
    row("golden: needs-a-person recall", lambda k: fmt(golden_m[k]["route"]["human_recall"]))
    row("golden: draft ready", lambda k: fmt(golden_m[k]["route"]["auto_share"]))
    row("**blind challenge: violations**", blind_cell(_violations))
    row("blind challenge: failures", blind_cell(lambda m: str(m["failures"]["count"])))
    row("blind challenge: route accuracy", blind_cell(lambda m: fmt(m["route"]["accuracy"])))
    row("blind challenge: needs-a-person recall", blind_cell(
        lambda m: fmt(m["route"]["human_recall"])
    ))  # fmt: skip
    row("blind challenge: draft ready", blind_cell(lambda m: fmt(m["route"]["auto_share"])))
    cost = {
        k: json.loads((run_dir(golden, k) / "metrics.json").read_text())["cost"] for k in CONFIGS
    }
    row("API cost per ticket, warm / cold cache", lambda k: (
        f"${cost[k]['usd_per_ticket_warm']:.5f} / ${cost[k]['usd_per_ticket_cold']:.5f}"
    ))  # fmt: skip
    row("p50 classify / end to end (CLI), s", lambda k: (
        f"{golden_m[k]['latency_ms']['classify']['p50'] / 1000:.2f} / "
        f"{golden_m[k]['latency_ms']['total']['p50'] / 1000:.1f}"
    ))  # fmt: skip

    jev, llm = (golden_cards[k] for k in (RECOMMENDED, "llm+haiku"))
    ok = {
        k: {c["ticket_id"]: not c.get("error") and labels[c["ticket_id"]]["route"] == c["route"]
            for c in cards}
        for k, cards in (("jev", jev), ("llm", llm))
    }  # fmt: skip
    ids = sorted(ok["jev"])
    a, b = [ok["jev"][t] for t in ids], [ok["llm"][t] for t in ids]
    only_a, only_b = discordant(a, b)
    lines += [
        "",
        f"Jev vs the LLM classifier (both with Haiku), route right on the same {len(ids)} golden "
        f"tickets: {sum(a)} vs {sum(b)}; right for one "
        f"only: Jev {only_a}, LLM {only_b}; exact McNemar p = {mcnemar(a, b):.2f}.",
    ]
    return "\n".join(lines)


def update_doc(block: str) -> None:
    """Rewrite the generated headline block in docs/evals.md."""
    head, _, tail = split(DOC.read_text(), "headline")
    DOC.write_text(f"{head}<!-- generated:headline -->\n{block}\n<!-- /generated -->{tail}")


def main() -> None:
    """Print the table; with --update-doc, write it into the doc."""
    parser = argparse.ArgumentParser(prog="evals.headline")
    parser.add_argument("--golden", required=True, help="results dir with all four configurations")
    parser.add_argument("--challenge", required=True, help="results dir of the blind set")
    parser.add_argument("--update-doc", action="store_true", help=f"rewrite the table in {DOC}")
    args = parser.parse_args()
    block = headline_table(args.golden, args.challenge)
    if args.update_doc:
        update_doc(block)
    print(block)


if __name__ == "__main__":
    main()

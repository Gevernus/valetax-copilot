"""Run the golden set through one configuration, or rebuild the summary from saved runs.

    uv run python -m evals.run run --classifier jev --model haiku
    uv run python -m evals.run report

A run writes evals/results/<date>/<classifier>+<model>/{cards,traces}.jsonl; `report` (also called
at the end of every run) recomputes metrics from saved cards and writes evals/results/<date>.json
and <date>.md. Re-scoring never calls a model.
"""

import argparse
import json
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Any

from copilot.classify import make_classifier
from copilot.classify.llm import SCHEMA as CLASSIFY_SCHEMA
from copilot.classify.llm import SYSTEM as CLASSIFY_SYSTEM
from copilot.draft import Drafter, schema, system_prompt
from copilot.kb import KnowledgeBase, load_kb
from copilot.llm import ClaudeCli, make_llm
from copilot.masking import mask_pii
from copilot.pipeline import Copilot
from evals.metrics import compute

ROOT = Path(__file__).resolve().parent
TICKETS = ROOT / "tickets.jsonl"
RESULTS = ROOT / "results"

# USD per million tokens. Anthropic: list prices for claude-haiku-5-5 and claude-sonnet-5-5
# (claude-api reference, cached 2026-10-06); cache read 0.1x and 5-minute cache write 1.25x of input.
# Jev: $0.042/M input, output free -- third-party figure, not confirmed on TypeSafe's own pages.
PRICES = {
    "claude-haiku-5-5": {"input": 0.10, "output": 0.50},
    "claude-sonnet-5-5": {"input": 2.00, "output": 10.00},
}
CACHE_READ, CACHE_WRITE = 0.1, 1.25
JEV_INPUT_PER_M = 0.042


def load_labels() -> dict[str, dict[str, Any]]:
    rows = [json.loads(line) for line in TICKETS.read_text().splitlines() if line.strip()]
    return {r["id"]: r for r in rows}


def check_labels(labels: dict[str, dict[str, Any]], kb: KnowledgeBase) -> None:
    for tid, lab in labels.items():
        unknown = set(lab["sections"]) - kb.sections.keys()
        if unknown:
            raise SystemExit(f"{tid}: label cites unknown sections {sorted(unknown)}")


def calibrate(llm: ClaudeCli, system: str, schema_: dict[str, Any]) -> dict[str, int]:
    """Our system prompt's size in tokens, net of the CLI's own prompt.

    The CLI adds ~8-12k tokens of its own, and that amount shifts between calls, so it cannot be
    subtracted per call. The same request with the system prompt doubled carries the same
    overhead; the difference is exactly one copy of our system prompt.
    """
    once = llm.complete(system, ".", schema_).usage.prompt_tokens
    twice = llm.complete(f"{system}\n\n{system}", ".", schema_).usage.prompt_tokens
    return {"system": max(0, twice - once)}


def run(args: argparse.Namespace) -> None:
    kb = load_kb()
    labels = load_labels()
    check_labels(labels, kb)
    ids = list(labels)[: args.limit] if args.limit else list(labels)

    llm = make_llm(args.llm, args.model)
    copilot = Copilot(kb, make_classifier(args.classifier), Drafter(llm, kb))
    config = f"{args.classifier}+{args.model}"
    out = RESULTS / args.date / config
    out.mkdir(parents=True, exist_ok=True)

    calibration: dict[str, Any] = {}
    if isinstance(llm, ClaudeCli):
        calibration["drafter"] = calibrate(llm, system_prompt(kb), schema(kb))
    if args.classifier == "llm":
        calibration["classifier"] = calibrate(ClaudeCli("haiku"), CLASSIFY_SYSTEM, CLASSIFY_SCHEMA)

    def one(tid: str) -> dict[str, Any]:
        text = labels[tid]["text"]
        for attempt in (1, 2):
            try:
                card = copilot.process(tid, text).to_dict()
                break
            except Exception as e:  # a transient API error should not lose the whole run
                if attempt == 2:
                    raise
                print(f"{tid}: retry after {type(e).__name__}", file=sys.stderr)
                time.sleep(2)
        card["ticket"] = mask_pii(text).text
        print(f"{tid}: {card['route']:5} {','.join(card['reasons'])}", file=sys.stderr)
        return card

    started = time.perf_counter()
    if args.classifier == "laya":
        copilot.classifier.classify("warm-up")  # load the checkpoint outside the timings
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        cards = list(pool.map(one, ids))
    wall_s = round(time.perf_counter() - started, 1)

    with (out / "cards.jsonl").open("w") as f:
        for card in cards:
            f.write(json.dumps(card, ensure_ascii=False) + "\n")
    with (out / "traces.jsonl").open("w") as f:
        for card in cards:
            trace = {k: v for k, v in card.items() if k in _TRACE_KEYS}
            f.write(json.dumps(trace, ensure_ascii=False) + "\n")
    meta = {
        "config": config,
        "classifier": args.classifier,
        "llm_backend": args.llm,
        "drafter_model": llm.model,
        "kb_version": kb.version,
        "tickets": len(cards),
        "workers": args.workers,
        "wall_s": wall_s,
        "calibration": calibration,
    }
    (out / "run.json").write_text(json.dumps(meta, indent=2))
    report(args.date)


_TRACE_KEYS = {"ticket_id", "route", "reasons", "category", "urgency", "language", "flags",
               "rule_hits", "citations", "masked", "timings_ms", "classifier", "drafter",
               "kb_version", "prompt_version", "draft_mode"}  # fmt: skip


def _user_tokens(card: dict[str, Any]) -> int:
    # The per-ticket message is short (mode, language, ticket); 3 characters per token is
    # conservative for English and close for Cyrillic and Arabic.
    return 20 + len(card["ticket"]) // 3


def cost_per_ticket(cards: list[dict[str, Any]], meta: dict[str, Any]) -> dict[str, Any]:
    """API cost of our own tokens: the calibrated system prompt priced as a cache read (warm) or a
    5-minute cache write (cold), the ticket message at the input price, and output tokens as
    measured (they include adaptive thinking, so they are an upper bound for an API call at low
    effort)."""
    cal = meta.get("calibration", {})
    price = PRICES[meta["drafter_model"]]

    def llm_cost(system: int, user: int, output: int, p: dict[str, float]) -> tuple[float, float]:
        base = (user * p["input"] + output * p["output"]) / 1e6
        return (
            base + system * p["input"] * CACHE_READ / 1e6,
            base + system * p["input"] * CACHE_WRITE / 1e6,
        )

    warm: list[float] = []
    cold: list[float] = []
    prompt_tokens: list[int] = []
    for card in cards:
        w = c = 0.0
        cls = card["classifier"]
        if cls["backend"] == "jev":
            w = c = cls["input_tokens"] * JEV_INPUT_PER_M / 1e6
        elif cls["backend"] == "llm":
            w, c = llm_cost(
                cal["classifier"]["system"], _user_tokens(card), cls["output_tokens"],
                PRICES["claude-haiku-5-5"],
            )  # fmt: skip
        if card["draft_mode"]:
            # claude-cli: calibrated; anthropic: the cached part the API reports.
            d = card["drafter"]
            system = cal.get("drafter", {}).get("system") or (
                d["cache_read_tokens"] + d["cache_write_tokens"]
            )
            dw, dc = llm_cost(system, _user_tokens(card), card["drafter"]["output_tokens"], price)
            w, c = w + dw, c + dc
            prompt_tokens.append(system + _user_tokens(card))
        warm.append(w)
        cold.append(c)
    return {
        "usd_per_ticket_warm": round(statistics.fmean(warm), 6),
        "usd_per_ticket_cold": round(statistics.fmean(cold), 6),
        "usd_per_10k_warm": round(statistics.fmean(warm) * 10_000, 2),
        "usd_per_10k_cold": round(statistics.fmean(cold) * 10_000, 2),
        "drafter_our_prompt_tokens_mean": round(statistics.fmean(prompt_tokens), 1)
        if prompt_tokens
        else 0,
    }


def report(day: str) -> None:
    kb = load_kb()
    labels = load_labels()
    runs: dict[str, Any] = {}
    for run_dir in sorted((RESULTS / day).iterdir()):
        if not (run_dir / "cards.jsonl").exists():
            continue
        cards = [json.loads(line) for line in (run_dir / "cards.jsonl").read_text().splitlines()]
        meta = json.loads((run_dir / "run.json").read_text())
        metrics = compute(labels, cards, kb)
        holdout = [c for c in cards if labels[c["ticket_id"]]["split"] == "holdout"]
        if holdout:
            h = compute(labels, holdout, kb)
            metrics["holdout"] = {"route": h["route"], "violations": h["violations"]}
        metrics["cost"] = cost_per_ticket(cards, meta)
        metrics["meta"] = meta
        (run_dir / "metrics.json").write_text(json.dumps(metrics, indent=2, ensure_ascii=False))
        runs[run_dir.name] = metrics
    (RESULTS / f"{day}.json").write_text(json.dumps(runs, indent=2, ensure_ascii=False))
    (RESULTS / f"{day}.md").write_text(summary_markdown(day, runs))
    print(f"wrote {RESULTS / f'{day}.md'}")


def _fmt(r: dict[str, Any]) -> str:
    if r["value"] is None:
        return "–"
    lo, hi = r["ci95"]
    return f"{r['value']:.0%} ({r['hits']}/{r['n']}, {lo:.0%}–{hi:.0%})"


def summary_markdown(day: str, runs: dict[str, Any]) -> str:
    names = list(runs)
    lines = [
        f"# Eval results {day}",
        "",
        f"Golden set: {next(iter(runs.values()))['n'] if runs else 0} hand-labelled tickets "
        "(evals/tickets.jsonl). Cells: value (hits/n, Wilson 95% CI).",
        "",
        "| metric | " + " | ".join(names) + " |",
        "|---|" + "---|" * len(names),
    ]

    def row(title: str, get: Any) -> None:
        lines.append(f"| {title} | " + " | ".join(get(runs[n]) for n in names) + " |")

    row("**hard-rule violations**", lambda m: f"**{m['violations']['count']}**")
    row("route accuracy", lambda m: _fmt(m["route"]["accuracy"]))
    row(
        "route accuracy, holdout only",
        lambda m: _fmt(m["holdout"]["route"]["accuracy"]) if "holdout" in m else "–",
    )
    row("needs-a-person recall (safety)", lambda m: _fmt(m["route"]["human_recall"]))
    row("draft-ready precision", lambda m: _fmt(m["route"]["auto_precision"]))
    row("draft-ready recall", lambda m: _fmt(m["route"]["auto_recall"]))
    row("draft-ready share", lambda m: _fmt(m["route"]["auto_share"]))
    for f in ("category", "urgency", "sentiment", "language"):
        row(f"{f} accuracy", lambda m, f=f: _fmt(m["fields"][f]))
    for flag in (
        "trading_advice",
        "complaint",
        "kyc_case",
        "aml_case",
        "injection",
        "account_lookup",
    ):
        row(f"{flag} recall / precision", lambda m, flag=flag: (
            f"{_short(m['flags'][flag]['recall'])} / {_short(m['flags'][flag]['precision'])}"
            f" (model only {_short(m['flags'][flag]['model_only_recall'])})"
        ))  # fmt: skip
    row(
        "abstain recall / precision",
        lambda m: f"{_short(m['abstain']['recall'])} / {_short(m['abstain']['precision'])}",
    )
    row("citations valid", lambda m: _fmt(m["citations"]["valid"]))
    row("expected section cited", lambda m: _fmt(m["citations"]["expected_hit"]))
    row("drafts withheld by grounding check", lambda m: str(len(m["grounding_rejections"])))
    row(
        "latency p50 / p95, s",
        lambda m: (
            f"{m['latency_ms']['total']['p50'] / 1000:.1f} / {m['latency_ms']['total']['p95'] / 1000:.1f}"
        ),
    )
    row("classify p50, ms", lambda m: str(m["latency_ms"].get("classify", {}).get("p50", "–")))
    row(
        "API cost per ticket, warm / cold cache",
        lambda m: (
            f"${m['cost']['usd_per_ticket_warm']:.5f} / ${m['cost']['usd_per_ticket_cold']:.5f}"
        ),
    )
    row("drafter prompt tokens (ours)", lambda m: str(m["cost"]["drafter_our_prompt_tokens_mean"]))
    row("drafter output tokens", lambda m: str(m["tokens_mean"]["drafter_output"]))

    lines += ["", "## Violations, missed and needless escalations", ""]
    for n in names:
        m = runs[n]
        lines.append(f"**{n}**")
        lines.append("")
        for tid, v in m["violations"]["tickets"].items():
            lines.append(f"- violation {tid}: {'; '.join(v)}")
        lines.append(
            f"- missed escalations: {', '.join(m['route']['missed_escalations']) or 'none'}"
        )
        lines.append(
            f"- needless escalations: {', '.join(m['route']['needless_escalations']) or 'none'}"
        )
        lines.append(
            f"- withheld by grounding check: {', '.join(m['grounding_rejections']) or 'none'}"
        )
        lines.append("")
    return "\n".join(lines) + "\n"


def _short(r: dict[str, Any]) -> str:
    return "–" if r["value"] is None else f"{r['value']:.0%} ({r['hits']}/{r['n']})"


def _today() -> str:
    return datetime.now().astimezone().date().isoformat()


def main() -> None:
    parser = argparse.ArgumentParser(prog="evals.run")
    sub = parser.add_subparsers(dest="command", required=True)
    r = sub.add_parser("run")
    r.add_argument("--classifier", choices=["jev", "laya", "llm"], default="jev")
    r.add_argument("--llm", choices=["claude-cli", "anthropic"], default="claude-cli")
    r.add_argument("--model", default="haiku")
    r.add_argument("--workers", type=int, default=4)
    r.add_argument("--limit", type=int)
    r.add_argument("--date", default=_today())
    rep = sub.add_parser("report")
    rep.add_argument("--date", default=_today())
    args = parser.parse_args()
    if args.command == "run":
        run(args)
    else:
        report(args.date)


if __name__ == "__main__":
    main()

"""Run the golden set through one configuration, or rebuild the summary from saved runs.

    uv run python -m evals.run run --classifier jev --model haiku
    uv run python -m evals.run report

A run writes evals/results/<date>/<classifier>+<model>/{cards,traces}.jsonl; `report` (also called
at the end of every run) recomputes metrics from saved cards and writes evals/results/<date>.json
and <date>.md. Re-scoring never calls a model.
"""

import argparse
import json
import shutil
import statistics
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Any

from copilot.classify import MEASURED_REPLY_CHECKERS, make_classifier, make_reply_checker
from copilot.classify.llm import SCHEMA as CLASSIFY_SCHEMA
from copilot.classify.llm import SYSTEM as CLASSIFY_SYSTEM
from copilot.draft import Drafter, schema, system_prompt
from copilot.errors import UsageLimitError
from copilot.kb import KnowledgeBase, load_kb
from copilot.llm import ClaudeCli, make_llm
from copilot.pipeline import Copilot
from evals.metrics import compute
from evals.prices import run_cost, user_tokens

ROOT = Path(__file__).resolve().parent
TICKETS = ROOT / "tickets.jsonl"
RESULTS = ROOT / "results"


class OutageError(RuntimeError):
    """Too many provider failures in a row: the run measures the outage, not the co-pilot."""


class OutageGuard:
    """Stops a run after `limit` cards in a row failed on a provider (the card has an `error`);
    a card that went through resets the count."""

    def __init__(self, limit: int = 5) -> None:
        self.limit = limit
        self._in_a_row = 0
        self._lock = threading.Lock()

    def record(self, card: dict[str, Any]) -> None:
        with self._lock:
            self._in_a_row = self._in_a_row + 1 if card.get("error") else 0
            if self._in_a_row >= self.limit:
                raise OutageError(f"{self._in_a_row} provider failures in a row")


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
    copilot = Copilot(
        kb,
        make_classifier(args.classifier),
        Drafter(llm, kb),
        reply_checker=make_reply_checker(args.reply_checker),
        raise_usage_limit=True,  # a run out of quota is discarded, not scored
    )
    config = f"{args.classifier}+{args.model}+reply-{args.reply_checker}"
    out = RESULTS / args.date / config
    out.mkdir(parents=True, exist_ok=True)

    calibration: dict[str, Any] = {}
    if isinstance(llm, ClaudeCli):
        calibration["drafter"] = calibrate(llm, system_prompt(kb), schema(kb))
    if args.classifier == "llm":
        calibration["classifier"] = calibrate(ClaudeCli("haiku"), CLASSIFY_SYSTEM, CLASSIFY_SCHEMA)

    stopped: list[Exception] = []  # the first reason to stop: a usage limit or an outage
    outage = OutageGuard()

    def one(tid: str) -> tuple[dict[str, Any], dict[str, Any]]:
        if stopped:
            raise stopped[0]
        text = labels[tid]["text"]
        try:
            # Failures end as cards for a person, retried inside the pipeline; the eval export
            # keeps the model's raw reply, which the agent's export leaves out.
            processed = copilot.process(tid, text)
        except UsageLimitError as e:
            # Quota is not a model failure: stop the run rather than score it.
            stopped.append(e)
            raise
        card = processed.to_eval_dict()  # its `ticket` is the text the models saw
        try:
            outage.record(card)
        except OutageError as e:
            stopped.append(e)  # the other workers stop too
            raise
        print(f"{tid}: {card['route']:5} {','.join(card['reasons'])}", file=sys.stderr)
        return card, processed.trace()

    started = time.perf_counter()
    if args.classifier == "laya":
        copilot.classifier.classify("warm-up")  # load the checkpoint outside the timings
    try:
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            results = list(pool.map(one, ids))
    except UsageLimitError:
        shutil.rmtree(out)
        raise SystemExit(f"{config}: usage limit reached; run discarded, nothing scored") from None
    except OutageError as e:
        shutil.rmtree(out)
        raise SystemExit(f"{config}: {e}; run discarded, nothing scored") from None
    wall_s = round(time.perf_counter() - started, 1)
    cards = [card for card, _ in results]

    with (out / "cards.jsonl").open("w") as f:
        for card in cards:
            f.write(json.dumps(card, ensure_ascii=False) + "\n")
    with (out / "traces.jsonl").open("w") as f:
        for _, trace in results:  # the same line the CLI writes: Card.trace()
            f.write(json.dumps(trace, ensure_ascii=False) + "\n")
    meta = {
        "config": config,
        "classifier": args.classifier,
        "reply_checker": args.reply_checker,
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


def cost_per_ticket(cards: list[dict[str, Any]], meta: dict[str, Any]) -> dict[str, Any]:
    """API cost of our own tokens (evals/prices.py): every system prompt a cache hit (warm) or a
    5-minute cache write (cold); the Jev reply check included, estimated on runs before it
    recorded its tokens."""
    warm = run_cost(cards, meta, hit_draft=1.0, hit_classify=1.0)
    cold = run_cost(cards, meta, hit_draft=0.0, hit_classify=0.0)
    system = meta.get("calibration", {}).get("drafter", {}).get("system")
    prompts = [
        (system or c["drafter"]["cache_read_tokens"] + c["drafter"]["cache_write_tokens"])
        + user_tokens(c)
        for c in cards
        if c["drafter"]["model"]
    ]
    return {
        "drafter_our_prompt_tokens_mean": round(statistics.fmean(prompts), 1) if prompts else 0,
        "usd_per_ticket_warm": round(warm.total, 6),
        "usd_per_ticket_cold": round(cold.total, 6),
        "usd_per_10k_warm": round(warm.total * 10_000, 2),
        "usd_per_10k_cold": round(cold.total * 10_000, 2),
        "usd_per_ticket_reply_check": round(warm.reply_check, 6),
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
    row(
        "failures (sent to a person, not scored)",
        lambda m: str(m.get("failures", {}).get("count", 0)),
    )
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
    r.add_argument("--reply-checker", choices=[*MEASURED_REPLY_CHECKERS, "none"], default="jev")
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

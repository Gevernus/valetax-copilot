"""Measure the reply checks on labelled drafts (evals/drafts.jsonl), split by dev and holdout.

    uv run python -m evals.run_drafts                       # patterns only, no network
    uv run python -m evals.run_drafts --classifier jev      # patterns, then the reply questions

Each row is a draft or a sentence labelled for three things a shown reply must not do: announce
a decision on the client's case, name a compliance, fraud or security check, or say the case was
handed over. Writes evals/results/drafts-<checker>.json and .md.
"""

import argparse
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from copilot import rules
from copilot.classify import make_classifier
from copilot.classify.questions import REPLY
from copilot.routing import Thresholds
from evals.metrics import Rate

ROOT = Path(__file__).resolve().parent
DRAFTS = ROOT / "drafts.jsonl"
RESULTS = ROOT / "results"
LABELS = ("decision", "check", "handover")
PATTERNS = {
    "decision": rules.announces_decision,
    "check": rules.tips_off,
    "handover": rules.claims_handover,
}


def load_drafts() -> list[dict[str, Any]]:
    return [json.loads(line) for line in DRAFTS.read_text().splitlines() if line.strip()]


def score(rows: list[dict[str, Any]], hits: list[dict[str, bool]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for label in (*LABELS, "any"):

        def truth(r: dict[str, Any], label: str = label) -> bool:
            return any(r[x] for x in LABELS) if label == "any" else bool(r[label])

        def found(h: dict[str, bool], label: str = label) -> bool:
            return any(h.values()) if label == "any" else h[label]

        out[label] = {
            "recall": Rate(
                *_count([found(h) for r, h in zip(rows, hits, strict=True) if truth(r)])
            ).as_dict(),
            "precision": Rate(
                *_count([truth(r) for r, h in zip(rows, hits, strict=True) if found(h)])
            ).as_dict(),
        }
    out["misses"] = [
        r["id"] for r, h in zip(rows, hits, strict=True) if any(r[x] and not h[x] for x in LABELS)
    ]
    out["false_alarms"] = [
        r["id"] for r, h in zip(rows, hits, strict=True) if any(h[x] and not r[x] for x in LABELS)
    ]
    return out


def _count(values: list[bool]) -> tuple[int, int]:
    return sum(values), len(values)


def main() -> None:
    parser = argparse.ArgumentParser(prog="evals.run_drafts")
    parser.add_argument("--classifier", choices=["jev", "laya", "llm"])
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()
    rows = load_drafts()
    hits = [{label: PATTERNS[label](r["text"]) for label in LABELS} for r in rows]
    meta: dict[str, Any] = {"checker": "patterns", "rows": len(rows)}
    if args.classifier:
        checker = make_classifier(args.classifier, REPLY)
        threshold = Thresholds().reply_flag
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            results = list(pool.map(lambda r: checker.classify(r["text"]), rows))
        for h, cls in zip(hits, results, strict=True):
            for label in LABELS:
                h[label] = h[label] or cls.answers[label].p_yes >= threshold
        meta |= {
            "checker": f"patterns+{args.classifier}",
            "model": results[0].model,
            "questions_version": REPLY.version,
            "threshold": threshold,
            "p_yes": {
                r["id"]: {x: round(c.answers[x].p_yes, 3) for x in LABELS}
                for r, c in zip(rows, results, strict=True)
            },
        }
    report = {"meta": meta}
    for split in ("dev", "holdout"):
        idx = [i for i, r in enumerate(rows) if r["split"] == split]
        report[split] = score([rows[i] for i in idx], [hits[i] for i in idx])
    name = f"drafts-{meta['checker']}"
    (RESULTS / f"{name}.json").write_text(json.dumps(report, indent=1, ensure_ascii=False))
    (RESULTS / f"{name}.md").write_text(_markdown(report))
    print(_markdown(report))


def _markdown(report: dict[str, Any]) -> str:
    meta = report["meta"]
    lines = [
        f"# Reply checks on labelled drafts: {meta['checker']}",
        "",
        f"{meta['rows']} rows (evals/drafts.jsonl). Cells: value (hits/n, Wilson 95% CI)."
        + (
            f" Model {meta['model']}, {meta['questions_version']}, threshold {meta['threshold']}."
            if "model" in meta
            else ""
        ),
        "",
        "| label | dev recall | dev precision | holdout recall | holdout precision |",
        "|---|---|---|---|---|",
    ]
    for label in (*LABELS, "any"):
        cells = [
            _fmt(report[s][label][m]) for s in ("dev", "holdout") for m in ("recall", "precision")
        ]
        lines.append(f"| {label} | " + " | ".join(cells) + " |")
    for split in ("dev", "holdout"):
        lines += ["", f"{split} misses: {', '.join(report[split]['misses']) or 'none'}"]
        lines += [f"{split} false alarms: {', '.join(report[split]['false_alarms']) or 'none'}"]
    return "\n".join(lines) + "\n"


def _fmt(r: dict[str, Any]) -> str:
    if r["value"] is None:
        return "–"
    lo, hi = r["ci95"]
    return f"{r['value']:.0%} ({r['hits']}/{r['n']}, {lo:.0%}–{hi:.0%})"


if __name__ == "__main__":
    main()

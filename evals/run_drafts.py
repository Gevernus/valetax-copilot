"""Measure the reply checks on labelled drafts (evals/drafts.jsonl), split by dev and holdout.

    uv run python -m evals.run_drafts                       # patterns only, no network
    uv run python -m evals.run_drafts --classifier jev      # also the REPLY questions
    uv run python -m evals.run_drafts --set drafts_challenge --classifier jev   # blind, never tuned on

Each row is a draft or a sentence labelled for three things a shown reply must not do: announce
a decision on the client's case, name a compliance, fraud or security check, or say the case was
handed over. With a classifier it reports three checkers side by side: the patterns alone, the
model alone, and both (what the pipeline runs). Writes evals/results/<set>-<checker>.json, .md.
"""

import argparse
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from copilot.classify import make_classifier
from copilot.classify.questions import REPLY
from copilot.reply_guard import GUARDS
from copilot.routing import Thresholds
from evals.metrics import fmt, read_jsonl, recall_precision

ROOT = Path(__file__).resolve().parent
SETS = {"drafts": ROOT / "drafts.jsonl", "drafts_challenge": ROOT / "drafts_challenge.jsonl"}
RESULTS = ROOT / "results"
LABELS = tuple(GUARDS)


def load_drafts(name: str = "drafts") -> list[dict[str, Any]]:
    """Rows with the three labels at the top level; the challenge set nests them in `labels`."""
    return [{**row, **row.get("labels", {})} for row in read_jsonl(SETS[name])]


def score(rows: list[dict[str, Any]], hits: list[dict[str, bool]]) -> dict[str, Any]:
    """Recall and precision per label and for any label, with misses and false alarms."""
    out: dict[str, Any] = {}
    pairs = list(zip(rows, hits, strict=True))
    for label in LABELS:
        out[label] = recall_precision([(bool(r[label]), h[label]) for r, h in pairs])
    out["any"] = recall_precision([(any(r[x] for x in LABELS), any(h.values())) for r, h in pairs])
    out["misses"] = [r["id"] for r, h in pairs if any(r[x] and not h[x] for x in LABELS)]
    out["false_alarms"] = [r["id"] for r, h in pairs if any(h[x] and not r[x] for x in LABELS)]
    return out


def main() -> None:
    """Run the checkers over a drafts set and write the report."""
    parser = argparse.ArgumentParser(prog="evals.run_drafts")
    parser.add_argument("--set", choices=list(SETS), default="drafts")
    parser.add_argument("--classifier", choices=["jev", "llm"])
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()
    rows = load_drafts(args.set)
    checkers: dict[str, list[dict[str, bool]]] = {
        "patterns": [{x: GUARDS[x].pattern(r["text"]) for x in LABELS} for r in rows]
    }
    meta: dict[str, Any] = {"set": args.set, "rows": len(rows), "checker": "patterns"}
    if args.classifier:
        model = make_classifier(args.classifier, REPLY)
        threshold = Thresholds().reply_flag
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            results = list(pool.map(lambda r: model.classify(r["text"]), rows))
        p_yes = [{x: c.answers[x].p_yes for x in LABELS} for c in results]
        checkers[args.classifier] = [{x: p[x] >= threshold for x in LABELS} for p in p_yes]
        checkers[f"patterns+{args.classifier}"] = [
            {x: a[x] or b[x] for x in LABELS}
            for a, b in zip(checkers["patterns"], checkers[args.classifier], strict=True)
        ]
        meta |= {
            "checker": f"patterns+{args.classifier}",
            "model": results[0].model,
            "questions_version": REPLY.version,
            "threshold": threshold,
            "p_yes": {
                r["id"]: {x: round(p[x], 3) for x in LABELS}
                for r, p in zip(rows, p_yes, strict=True)
            },
        }
    splits = sorted({r.get("split", "all") for r in rows})
    report: dict[str, Any] = {"meta": meta}
    for name, hits in checkers.items():
        report[name] = {}
        for split in splits:
            idx = [i for i, r in enumerate(rows) if r.get("split", "all") == split]
            report[name][split] = score([rows[i] for i in idx], [hits[i] for i in idx])
    stem = f"{args.set}-{meta['checker']}"
    (RESULTS / f"{stem}.json").write_text(json.dumps(report, indent=1, ensure_ascii=False))
    (RESULTS / f"{stem}.md").write_text(_markdown(report, list(checkers), splits))
    print(_markdown(report, list(checkers), splits))


def _markdown(report: dict[str, Any], checkers: list[str], splits: list[str]) -> str:
    meta = report["meta"]
    lines = [
        f"# Reply checks on {meta['set']}.jsonl: {', '.join(checkers)}",
        "",
        f"{meta['rows']} rows. Cells: recall / precision, each value (hits/n, Wilson 95% CI)."
        + (
            f" Model {meta['model']}, {meta['questions_version']}, threshold {meta['threshold']}."
            if "model" in meta
            else ""
        ),
    ]
    for split in splits:
        lines += ["", f"## {split}", "", "| label | " + " | ".join(checkers) + " |"]
        lines.append("|---|" + "---|" * len(checkers))
        for label in (*LABELS, "any"):
            cells = [
                f"{fmt(report[c][split][label]['recall'])} / "
                f"{fmt(report[c][split][label]['precision'])}"
                for c in checkers
            ]
            lines.append(f"| {label} | " + " | ".join(cells) + " |")
        last = report[checkers[-1]][split]
        lines += ["", f"{checkers[-1]} misses: {', '.join(last['misses']) or 'none'}"]
        lines += [f"{checkers[-1]} false alarms: {', '.join(last['false_alarms']) or 'none'}"]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    main()

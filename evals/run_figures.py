"""Measure the number layer alone on the blind figures set (evals/figures_challenge.jsonl).

    uv run python -m evals.run_figures

Each row is a draft with the sections it cites and the client's ticket, labelled for whether it
states a figure (number, unit, currency, time) the cited sections do not support. The deterministic
check runs per row, no model. Two predictions are scored: "withheld", a figure problem that keeps
the draft from being shown, and "flagged", withheld or shown with figures taken only from the
ticket (both send the ticket to a person). Written by a separate agent that never saw the code;
run once, never tuned on. Writes evals/results/figures_challenge-check_draft.json and .md.
"""

import json
from pathlib import Path
from typing import Any

from copilot.draft import Draft
from copilot.grounding import check_draft
from copilot.kb import KnowledgeBase, load_kb
from copilot.masking import mask_pii
from evals.metrics import fmt, read_jsonl, recall_precision

ROOT = Path(__file__).resolve().parent
FIGURES = ROOT / "figures_challenge.jsonl"
OUT = ROOT / "results" / "figures_challenge-check_draft"
GROUPS = {"en": ("en",), "ru-es": ("ru", "es")}
FIGURE_PROBLEMS = ("numbers not in", "time units not in", "unsupported policy claims")
OTHER_PROBLEMS = ("empty reply", "unknown sections", "no citations", "reply contains trading")


def group(lang: str) -> str:
    """Language group of a row for the report."""
    return next((name for name, langs in GROUPS.items() if lang in langs), "other")


def predict(row: dict[str, Any], kb: KnowledgeBase) -> dict[str, bool]:
    """Whether the source check withholds the draft, and whether it flags it."""
    draft = Draft(abstain=False, reply=row["draft"], citations=row["cited"])
    # The ticket as the pipeline gives it to the check: normalised and masked.
    result = check_draft(draft, kb, mask_pii(row["ticket"]).text)
    # A new kind of problem must be classed here as a figure problem or not, not ignored.
    unknown = [p for p in result.problems if not p.startswith(FIGURE_PROBLEMS + OTHER_PROBLEMS)]
    if unknown:
        raise ValueError(f"{row['id']}: unclassified problems {unknown}")
    withheld = any(p.startswith(FIGURE_PROBLEMS) for p in result.problems)
    return {"withheld": withheld, "flagged": withheld or bool(result.client_figures)}


def main() -> None:
    """Run the number layer over the figures set and write the report."""
    rows = read_jsonl(FIGURES)
    kb = load_kb()
    preds = [predict(r, kb) for r in rows]
    report: dict[str, Any] = {
        "rows": len(rows),
        "predictions": {r["id"]: p for r, p in zip(rows, preds, strict=True)},
    }
    for kind in ("withheld", "flagged"):
        report[kind] = {}
        for name in ("all", *GROUPS, "other"):
            pairs = [
                (r["label"]["unsupported_figure"], p[kind])
                for r, p in zip(rows, preds, strict=True)
                if name == "all" or group(r["lang"]) == name
            ]
            report[kind][name] = recall_precision(pairs)
        report[kind]["misses"] = [
            r["id"]
            for r, p in zip(rows, preds, strict=True)
            if r["label"]["unsupported_figure"] and not p[kind]
        ]
        report[kind]["false_alarms"] = [
            r["id"]
            for r, p in zip(rows, preds, strict=True)
            if p[kind] and not r["label"]["unsupported_figure"]
        ]
    OUT.with_suffix(".json").write_text(json.dumps(report, indent=1, ensure_ascii=False))
    OUT.with_suffix(".md").write_text(_markdown(report, {r["id"]: r for r in rows}))
    print(_markdown(report, {r["id"]: r for r in rows}))


def _markdown(report: dict[str, Any], rows: dict[str, dict[str, Any]]) -> str:
    lines = [
        "# Number layer on figures_challenge.jsonl (check_draft only, no model)",
        "",
        f"{report['rows']} rows. Cells: value (hits/n, Wilson 95% CI).",
    ]
    for kind in ("withheld", "flagged"):
        lines += ["", f"## {kind}", "", "| group | recall | precision |", "|---|---|---|"]
        for name in ("all", *GROUPS, "other"):
            cell = report[kind][name]
            lines.append(f"| {name} | {fmt(cell['recall'])} | {fmt(cell['precision'])} |")
        for title, key in (("misses", "misses"), ("false alarms", "false_alarms")):
            lines += ["", f"{kind} {title}:"]
            for rid in report[kind][key]:
                r = rows[rid]
                lines.append(
                    f"- {rid} ({r['lang']}) figure={r['figure']!r} note={r['note']!r}: {r['draft'][:120]}"
                )
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    main()

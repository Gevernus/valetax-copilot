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
from copilot.kb import load_kb
from evals.metrics import Rate

ROOT = Path(__file__).resolve().parent
FIGURES = ROOT / "figures_challenge.jsonl"
OUT = ROOT / "results" / "figures_challenge-check_draft"
GROUPS = {"en": ("en",), "ru-es": ("ru", "es")}
FIGURE_PROBLEMS = ("numbers not in", "time units not in", "unsupported policy claims")


def load_figures() -> list[dict[str, Any]]:
    return [json.loads(line) for line in FIGURES.read_text().splitlines() if line.strip()]


def group(lang: str) -> str:
    return next((name for name, langs in GROUPS.items() if lang in langs), "other")


def predict(row: dict[str, Any]) -> dict[str, bool]:
    kb = load_kb()
    draft = Draft(abstain=False, reply=row["draft"], citations=row["cited"])
    result = check_draft(draft, kb, row["ticket"])
    withheld = any(p.startswith(FIGURE_PROBLEMS) for p in result.problems)
    return {"withheld": withheld, "flagged": withheld or bool(result.client_figures)}


def score(pairs: list[tuple[bool, bool]]) -> dict[str, Any]:
    return {
        "recall": Rate(sum(p for t, p in pairs if t), sum(t for t, _ in pairs)).as_dict(),
        "precision": Rate(sum(t for t, p in pairs if p), sum(p for _, p in pairs)).as_dict(),
    }


def main() -> None:
    rows = load_figures()
    preds = [predict(r) for r in rows]
    report: dict[str, Any] = {"rows": len(rows)}
    for kind in ("withheld", "flagged"):
        report[kind] = {}
        for name in ("all", *GROUPS, "other"):
            pairs = [
                (r["label"]["unsupported_figure"], p[kind])
                for r, p in zip(rows, preds, strict=True)
                if name == "all" or group(r["lang"]) == name
            ]
            report[kind][name] = score(pairs)
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
            lines.append(f"| {name} | {_fmt(cell['recall'])} | {_fmt(cell['precision'])} |")
        for title, key in (("misses", "misses"), ("false withholds", "false_alarms")):
            lines += ["", f"{kind} {title}:"]
            for rid in report[kind][key]:
                r = rows[rid]
                lines.append(
                    f"- {rid} ({r['lang']}) figure={r['figure']!r} note={r['note']!r}: {r['draft'][:120]}"
                )
    return "\n".join(lines) + "\n"


def _fmt(r: dict[str, Any]) -> str:
    if r["value"] is None:
        return "–"
    lo, hi = r["ci95"]
    return f"{r['value']:.0%} ({r['hits']}/{r['n']}, {lo:.0%}–{hi:.0%})"


if __name__ == "__main__":
    main()

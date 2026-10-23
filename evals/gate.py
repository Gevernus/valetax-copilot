"""CI gate: saved model outputs through the current code must not lose quality.

    uv run python -m evals.gate 2026-10-23 2026-10-23-challenge

Every run in the given results dirs is replayed (`evals.run replay`, no network, reply check
by patterns only) and must keep zero hard-rule violations and a route accuracy no lower than
its committed metrics.json. A route moved on purpose is saved with `evals.run replay --write`
and listed in the commit; the gate then holds the new numbers. A prompt, question or KB change
needs a new run, not this gate.
"""

import json
import sys

from evals.run import RESULTS, replay_run


def main(dates: list[str]) -> int:
    """Exit status 1 when any run has a violation or lost route accuracy, or a dir has no run."""
    failed = 0
    for date in dates:
        runs = sorted(p for p in (RESULTS / date).glob("*") if (p / "metrics.json").exists())
        if not runs:  # a typo or an empty dir must not pass as "nothing regressed"
            print(f"FAIL {date}: no scored runs")
            failed += 1
        for run_dir in runs:
            committed = json.loads((run_dir / "metrics.json").read_text())["route"]["accuracy"]
            metrics = replay_run(f"{date}/{run_dir.name}")["metrics"]
            now, violations = metrics["route"]["accuracy"], metrics["violations"]["count"]
            ok = violations == 0 and now["value"] >= committed["value"]
            failed += not ok
            print(
                f"{'ok  ' if ok else 'FAIL'} {date}/{run_dir.name}: violations {violations}, "
                f"route accuracy {now['hits']}/{now['n']} (committed {committed['hits']}/"
                f"{committed['n']})"
            )
    return 1 if failed or not dates else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

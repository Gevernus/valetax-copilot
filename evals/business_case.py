"""The numbers behind docs/business-case.md, recomputed from a results file.

    uv run python -m evals.business_case --date 2026-10-22

Measured inputs come from the run; everything else is a labelled assumption below.
"""

import argparse
import json
from pathlib import Path

RESULTS = Path(__file__).resolve().parent / "results"

TICKETS_PER_MONTH = 10_000  # from the brief
# Share of handling time an agent saves (assumptions, see docs/business-case.md):
SAVED_READY = 0.50  # a draft ready to send after reading
SAVED_ASSISTED = (
    0.15  # a person decides, but classification, a drafted acknowledgement or partial answer exist
)
# Fixed monthly cost (assumptions): one small VM, 8 h of an engineer at $50/h for the weekly
# review and fixes, 4 h of the support lead at $20/h.
FIXED_PER_MONTH = 50 + 8 * 50 + 4 * 20
COST_PER_CONTACT = (2.0, 4.0, 6.0, 10.0)  # human cost per ticket, USD
READY_SHARE = (0.30, 0.50, 0.70)  # share of live tickets with a ready draft


def main() -> None:
    parser = argparse.ArgumentParser(prog="evals.business_case")
    parser.add_argument("--date", required=True)
    args = parser.parse_args()
    runs = json.loads((RESULTS / f"{args.date}.json").read_text())

    print(
        "| configuration | violations | route acc. | ready share | assisted share | model $/month (warm-cold) | total $/month |"
    )
    print("|---|---|---|---|---|---|---|")
    for name, m in runs.items():
        cards = [
            json.loads(line)
            for line in (RESULTS / args.date / name / "cards.jsonl").read_text().splitlines()
        ]
        ready = sum(c["route"] == "auto" for c in cards) / len(cards)
        assisted = sum(c["route"] == "human" and c["reply"] is not None for c in cards) / len(cards)
        warm = m["cost"]["usd_per_ticket_warm"] * TICKETS_PER_MONTH
        cold = m["cost"]["usd_per_ticket_cold"] * TICKETS_PER_MONTH
        print(
            f"| {name} | {m['violations']['count']} | {m['route']['accuracy']['value']:.0%} "
            f"| {ready:.0%} | {assisted:.0%} | {warm:.2f}–{cold:.2f} | {FIXED_PER_MONTH + cold:.0f} |"
        )

    print("\nMonthly saving, USD, with 20% of tickets assisted (sensitivity):\n")
    print("| cost per contact | " + " | ".join(f"ready {r:.0%}" for r in READY_SHARE) + " |")
    print("|---|" + "---|" * len(READY_SHARE))
    for cpc in COST_PER_CONTACT:
        cells = [
            TICKETS_PER_MONTH * cpc * (r * SAVED_READY + 0.20 * SAVED_ASSISTED) for r in READY_SHARE
        ]
        print(f"| ${cpc:.0f} | " + " | ".join(f"{c:,.0f}" for c in cells) + " |")

    floor = FIXED_PER_MONTH / (
        TICKETS_PER_MONTH * (READY_SHARE[0] * SAVED_READY + 0.20 * SAVED_ASSISTED)
    )
    print(
        f"\nBreak-even cost per contact at the low end ({READY_SHARE[0]:.0%} ready): ${floor:.2f}"
    )
    print(f"Fixed cost assumed: ${FIXED_PER_MONTH}/month")


if __name__ == "__main__":
    main()

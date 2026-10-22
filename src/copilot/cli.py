"""Command line: process one ticket, or render decision cards as a static page for agents."""

import argparse
import json
import sys
from pathlib import Path

from copilot.classify import make_classifier
from copilot.classify.questions import REPLY
from copilot.draft import Drafter
from copilot.kb import DEFAULT_KB, load_kb
from copilot.llm import make_llm
from copilot.pipeline import Card, Copilot
from copilot.trace import TraceWriter
from copilot.view import render_page


def build_copilot(classifier: str, llm: str, model: str, kb_path: Path = DEFAULT_KB) -> Copilot:
    kb = load_kb(kb_path)
    return Copilot(
        kb,
        make_classifier(classifier),
        Drafter(make_llm(llm, model), kb),
        reply_checker=make_classifier(classifier, REPLY),
    )


def _print_card(card: Card) -> None:
    print(f"ROUTE: {card.route.upper()}  priority={card.urgency}  [{card.ticket_id}]")
    for reason, consequence in zip(card.reasons, card.consequences, strict=True):
        print(f"  - {reason}: {consequence}")
    print(
        f"category={card.category} language={card.language} sentiment={card.sentiment} "
        f"draft_mode={card.draft_mode}"
    )
    print("\nDRAFT:")
    if card.reply is not None:
        print(card.reply)
    elif card.abstain_reason:
        print(f"(abstained: {card.abstain_reason})")
    elif card.problems:
        print("(withheld: " + "; ".join(card.problems) + ")")
    else:
        print("(none)")
    if card.client_figures:
        print("\nFROM THE CLIENT'S MESSAGE, NOT IN THE SOURCES:")
        for figure in card.client_figures:
            print(f"  - {figure}")
    if card.unanswered:
        print("\nNOT IN THE KNOWLEDGE BASE:")
        for q in card.unanswered:
            print(f"  - {q}")
    if card.citations:
        print("\nSOURCES:")
        for c in card.citations:
            print(f"  [{c['id']}] {c['title']} — {c['url']}")
    print(f"\ntimings_ms={card.timings_ms}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="copilot", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="process one ticket (text argument, --file, or stdin)")
    run.add_argument("text", nargs="?")
    run.add_argument("--file", type=Path)
    run.add_argument("--id", default="cli")
    run.add_argument("--classifier", choices=["jev", "laya", "llm"], default="jev")
    run.add_argument("--llm", choices=["claude-cli", "anthropic"], default="claude-cli")
    run.add_argument("--model", default="haiku", help="haiku, sonnet or a full model id")
    run.add_argument("--json", action="store_true", help="print the card as JSON")
    run.add_argument("--traces", type=Path, default=Path("traces/traces.jsonl"))

    view = sub.add_parser("view", help="render cards (JSONL) into one static HTML page")
    view.add_argument("cards", type=Path)
    view.add_argument("-o", "--out", type=Path, default=Path("agent-view.html"))

    args = parser.parse_args(argv)

    if args.command == "view":
        cards = [json.loads(line) for line in args.cards.read_text().splitlines() if line.strip()]
        args.out.write_text(render_page(cards))
        print(f"wrote {args.out} ({len(cards)} cards)")
        return 0

    if args.file:
        text = args.file.read_text()
    elif args.text:
        text = args.text
    else:
        text = sys.stdin.read()
    copilot = build_copilot(args.classifier, args.llm, args.model)
    card = copilot.process(args.id, text)
    TraceWriter(args.traces).write(card.trace())
    if args.json:
        print(json.dumps(card.to_dict(), ensure_ascii=False, indent=2))
    else:
        _print_card(card)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

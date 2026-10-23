"""Command line: process one ticket, or render decision cards as a static page for agents."""

import argparse
import json
import sys
from pathlib import Path

from copilot.classify import MEASURED_REPLY_CHECKERS, make_classifier, make_reply_checker
from copilot.draft import Drafter
from copilot.kb import DEFAULT_KB, load_kb
from copilot.llm import make_llm
from copilot.pipeline import MAX_RAW_CHARS, Card, Copilot
from copilot.trace import TraceWriter
from copilot.view import render_page


def build_copilot(
    classifier: str, llm: str, model: str, reply_checker: str, kb_path: Path = DEFAULT_KB
) -> Copilot:
    """The pipeline with the backends named on the command line."""
    kb = load_kb(kb_path)
    return Copilot(
        kb,
        make_classifier(classifier),
        Drafter(make_llm(llm, model), kb),
        reply_checker=make_reply_checker(reply_checker),
    )


def _print_json(card: Card) -> None:
    """The agent's export: never the model's withheld text."""
    print(json.dumps(card.to_dict(), ensure_ascii=False, indent=2))


def _print_card(card: Card) -> None:
    """Printed from the agent's view, like every other way out to the agent."""
    c = card.to_dict()
    print(f"ROUTE: {c['route'].upper()}  priority={c['urgency']}  [{c['ticket_id']}]")
    for reason, consequence in zip(c["reasons"], c["consequences"], strict=True):
        print(f"  - {reason}: {consequence}")
    print(
        f"category={c['category']} language={c['language']} sentiment={c['sentiment']} "
        f"draft_mode={c['draft_mode']}"
    )
    print("\nDRAFT:")
    if c["reply"] is not None:
        print(c["reply"])
    elif c["abstain_reason"]:
        print(f"(abstained: {c['abstain_reason']})")
    elif c["problems"]:
        print("(withheld: " + "; ".join(c["problems"]) + ")")
    else:
        print("(none)")
    _print_list("FROM THE CLIENT'S MESSAGE, NOT IN THE SOURCES", c["client_figures"])
    _print_list("NOT IN THE KNOWLEDGE BASE", c["unanswered"])
    sources = [f"[{s['id']}] {s['title']} — {s['url']}" for s in c["citations"]]
    _print_list("SOURCES", sources, bullet="")
    print(f"\ntimings_ms={c['timings_ms']}")


def _print_list(title: str, items: list[str], bullet: str = "- ") -> None:
    if items:
        print(f"\n{title}:")
        for item in items:
            print(f"  {bullet}{item}")


def _read_ticket(path: Path | None) -> str:
    """The ticket from a file or stdin, never argv (shell history, the process list).

    At most one character past the pipeline's limit is read, so a huge input is refused as too
    long without being held in memory. Both ways decode UTF-8 the same: a bad byte becomes
    U+FFFD whatever the locale, never an exception or a surrogate sent to a vendor.
    """
    if path is None:
        raw = sys.stdin.buffer.read(4 * (MAX_RAW_CHARS + 1))  # UTF-8: at most 4 bytes a character
        return raw.decode("utf-8", errors="replace")[: MAX_RAW_CHARS + 1]
    with path.open(encoding="utf-8", errors="replace") as f:
        return f.read(MAX_RAW_CHARS + 1)


def main(argv: list[str] | None = None) -> int:
    """Command line: `run` one ticket, or `view` cards as a page."""
    parser = argparse.ArgumentParser(prog="copilot", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="process one ticket from --file or stdin")
    run.add_argument("--file", type=Path, help="the ticket; stdin when absent")
    run.add_argument("--id", default="cli")
    run.add_argument("--classifier", choices=["jev", "llm"], default="jev")
    run.add_argument("--llm", choices=["claude-cli", "anthropic"], default="claude-cli")
    run.add_argument("--model", default="haiku", help="haiku, sonnet or a full model id")
    run.add_argument(
        "--reply-checker", choices=[*MEASURED_REPLY_CHECKERS, "none"], default="jev",
        help="backend for the REPLY questions; none = patterns only",
    )  # fmt: skip
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

    text = _read_ticket(args.file)
    copilot = build_copilot(args.classifier, args.llm, args.model, args.reply_checker)
    card = copilot.process(args.id, text)
    if args.json:
        _print_json(card)
    else:
        _print_card(card)
    try:  # the agent has the card; a trace that cannot be written is reported, not raised
        TraceWriter(args.traces).write(card.trace())
    except OSError as e:
        print(
            f"trace not written to {args.traces}: {e.strerror or type(e).__name__}", file=sys.stderr
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

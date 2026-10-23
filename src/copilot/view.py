"""Static agent view: the cards embedded as JSON into one self-contained HTML file."""

import json
from dataclasses import fields
from importlib.resources import files
from typing import Any

from copilot.pipeline import EVAL_ONLY, Card, agent_view

# What a page may show: the agent's export of a card, plus the masked ticket the evals add.
AGENT_FIELDS = frozenset(f.name for f in fields(Card)) - set(EVAL_ONLY) | {"ticket"}


def render_page(cards: list[dict[str, Any]]) -> str:
    """Cards from any source (a CLI run or an eval's cards.jsonl) keep only the agent's fields.
    In the embedded JSON, "<", ">" and "&" are escaped, so no string can close the data block or
    open a tag; the page's script escapes every value it writes into HTML."""
    template = files("copilot").joinpath("agent_view.html").read_text()
    shown = [{k: v for k, v in agent_view(card).items() if k in AGENT_FIELDS} for card in cards]
    data = json.dumps(shown, ensure_ascii=False)
    data = data.replace("&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e")
    return template.replace("/*CARDS*/", data)

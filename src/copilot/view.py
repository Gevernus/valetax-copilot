"""Static agent view: the cards embedded as JSON into one self-contained HTML file."""

import json
from importlib.resources import files
from typing import Any


def render_page(cards: list[dict[str, Any]]) -> str:
    template = files("copilot").joinpath("agent_view.html").read_text()
    # "</" inside a <script> block would end it early.
    data = json.dumps(cards, ensure_ascii=False).replace("</", "<\\/")
    return template.replace("/*CARDS*/", data)

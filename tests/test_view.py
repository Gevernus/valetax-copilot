"""The agent's view never carries withheld model text, and renders hostile strings as text."""

import json
import re
import shutil
import subprocess

import pytest

from copilot import cli
from copilot.view import AGENT_FIELDS, render_page
from test_pipeline import FakeClassifier, FakeLlm, make

HOSTILE = "<script>alert(1)</script> \" ' </textarea> <img src=x onerror=alert(2)>"


def withheld_card() -> dict[str, object]:
    llm = FakeLlm(reply="Deposits are free of charge.", citations=["funding.how-to-deposit"])
    return make(FakeClassifier(), llm).process("t", "fees?").to_dict()


def test_agent_export_has_no_withheld_text() -> None:
    card = withheld_card()
    assert "raw_reply" not in card
    assert card["reply"] is None
    assert "Deposits are free of charge" not in json.dumps(card)
    assert set(card) <= AGENT_FIELDS


def test_eval_export_keeps_the_raw_reply() -> None:
    llm = FakeLlm(reply="Deposits are free of charge.", citations=["funding.how-to-deposit"])
    card = make(FakeClassifier(), llm).process("t", "fees?").to_eval_dict()
    assert card["raw_reply"] == "Deposits are free of charge."


def test_cli_json_is_the_agent_export(capsys: pytest.CaptureFixture[str]) -> None:
    card = make(
        FakeClassifier(), FakeLlm(reply="Free of charge.", citations=["funding.how-to-deposit"])
    ).process("t", "?")
    cli._print_json(card)
    assert "raw_reply" not in capsys.readouterr().out


def test_the_page_drops_fields_the_agent_must_not_see() -> None:
    page = render_page([{"ticket_id": "t", "raw_reply": "SECRET withheld text", "route": "human"}])
    assert "SECRET withheld text" not in page


def test_hostile_strings_cannot_close_the_data_block() -> None:
    page = render_page([{"ticket_id": HOSTILE, "reply": HOSTILE}])
    data = re.search(r'<script id="data" type="application/json">(.*?)</script>', page, re.S)
    assert data is not None
    assert "<" not in data.group(1)  # nothing in the data can open or close a tag
    assert json.loads(data.group(1))[0]["reply"] == HOSTILE


@pytest.mark.skipif(shutil.which("node") is None, reason="node renders the page's script")
def test_hostile_strings_render_as_text() -> None:
    card = {
        "ticket_id": HOSTILE, "route": HOSTILE, "reasons": [HOSTILE], "consequences": [HOSTILE],
        "category": HOSTILE, "urgency": HOSTILE, "sentiment": HOSTILE, "language": HOSTILE,
        "reply": HOSTILE, "ticket": HOSTILE, "problems": [HOSTILE], "abstain_reason": "",
        "client_figures": [HOSTILE], "unanswered": [HOSTILE],
        "citations": [{"id": HOSTILE, "title": HOSTILE, "url": "javascript:alert(3)"}],
        "classifier": {"backend": HOSTILE}, "drafter": {"model": HOSTILE},
        "kb_version": HOSTILE, "timings_ms": {HOSTILE: HOSTILE},
    }  # fmt: skip
    page = render_page([card])
    script = page.rsplit("<script>", 1)[1].split("</script>", 1)[0]
    data = re.search(r'<script id="data" type="application/json">(.*?)</script>', page, re.S)
    assert data is not None
    harness = (
        "const els = {}; const el = (id) => (els[id] ??= {innerHTML: '', textContent: '',"
        " addEventListener() {}, querySelectorAll: () => [], setAttribute() {}, dataset: {}});"
        "globalThis.document = {getElementById: (id) => id === 'data' ? {textContent: DATA} : el(id),"
        " querySelectorAll: () => [], addEventListener() {}};"
        "globalThis.navigator = {clipboard: {writeText() {}}};"
        f"const DATA = {json.dumps(data.group(1))};\n{script}\n"
        "process.stdout.write(els.cards.innerHTML);"
    )
    out = subprocess.run(  # noqa: S603 - our own page script, run to check its escaping
        ["node", "-e", harness],  # noqa: S607
        capture_output=True, text=True, check=True, timeout=30,
    ).stdout  # fmt: skip
    assert "<script" not in out
    assert "<img" not in out
    assert "javascript:" not in out
    assert "&lt;script&gt;" in out
    assert "&#39;" in out
    assert "&quot;" in out

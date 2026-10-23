"""The agent's view never carries withheld model text, and renders hostile strings as text."""

import json
import re
import shutil
import subprocess

import pytest

from copilot import cli
from copilot.pipeline import Card
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


def test_model_text_is_cleared_with_a_withheld_draft() -> None:
    from copilot.pipeline import EVAL_ONLY

    llm = FakeLlm(
        reply="Your account is under compliance review.",
        citations=["funding.withdrawal-pending"],
        unanswered=["whether the AML investigation on your account is finished"],
    )
    card = make(FakeClassifier(), llm).process("t", "why is my withdrawal pending?")
    agent = card.to_dict()
    assert agent["reply"] is None
    assert agent["unanswered"] == []
    assert agent["abstain_reason"] == ""
    assert "AML investigation" not in json.dumps(agent)
    full = card.to_eval_dict()
    assert full["unanswered"] == ["whether the AML investigation on your account is finished"]
    assert set(EVAL_ONLY) <= set(full)


def test_shown_model_text_is_checked_by_the_patterns() -> None:
    llm = FakeLlm(
        reply="The minimum deposit starts from 8 USD, depending on the account type.",
        citations=["funding.min-deposit"],
        unanswered=["whether the compliance review of your account is finished"],
    )
    card = make(FakeClassifier(), llm).process("t", "min deposit? and is my review done?")
    assert "tipping_off" in card.reasons
    assert card.reply is None
    assert card.to_dict()["unanswered"] == []


def tipping_off_card() -> Card:
    llm = FakeLlm(
        reply="Your account is under compliance review.",
        citations=["funding.withdrawal-pending"],
        unanswered=["whether the AML investigation on your account is finished"],
    )
    return make(FakeClassifier(), llm).process("t", "why is my withdrawal pending?")


def test_the_cli_prints_only_the_agent_view(capsys: pytest.CaptureFixture[str]) -> None:
    cli._print_card(tipping_off_card())
    assert "AML" not in capsys.readouterr().out


def test_the_page_shows_only_the_agent_view_of_an_eval_card() -> None:
    assert "AML" not in render_page([tipping_off_card().to_eval_dict()])


def test_cards_saved_before_the_withheld_field_are_cleared_too() -> None:
    from copilot.pipeline import agent_view

    old = {"reply": None, "raw_reply": "x", "problems": [], "unanswered": ["AML?"],
           "abstain_reason": ""}  # fmt: skip
    assert agent_view(old)["unanswered"] == []
    old = {"reply": None, "problems": ["numbers not in cited sections: 3"],
           "unanswered": ["AML?"], "abstain_reason": ""}  # fmt: skip
    assert agent_view(old)["unanswered"] == []

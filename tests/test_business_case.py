"""The cost and saving formulas checked by hand, and the doc checked against the script."""

import json
import re

import pytest
from evals import business_case as bc
from evals import prices

DOC = bc.DOC.read_text()
# The doc names its run in the generated caption: one source, so `--date <new> --update-doc` holds.
DATE = re.findall(r"Run `([^`]+)`", DOC)[0]


def test_monthly_saving_by_hand() -> None:
    # 1,000 tickets x 40% ready x $4 a contact x 25% of the time saved = $400.
    assert bc.monthly_saving(1_000, 4.0, 0.40, 0.25) == pytest.approx(400)


def test_break_even_per_incoming_and_per_ready_ticket() -> None:
    assert bc.break_even(535, 10_000) == pytest.approx(0.0535)
    assert bc.break_even(535, 10_000, share=0.20) == pytest.approx(0.2675)


def test_cost_of_one_call_by_hand() -> None:
    # Haiku 5.5, 2,000-token prefix, half the calls hit: 2000 x (0.5 x 0.01 + 0.5 x 0.125) = 135;
    # 100 x 0.10 = 10; 500 x 0.50 = 250 -> $395 per million calls.
    cost = prices.llm_call_cost("claude-haiku-5-5", 2_000, 100, 500, hit=0.5)
    assert cost == pytest.approx(395e-6)
    # Below the 512-token minimum the prefix is plain input: 400 x 0.10 + 10 + 250 = 300.
    assert prices.llm_call_cost("claude-haiku-5-5", 400, 100, 500, hit=0.5) == pytest.approx(300e-6)


def test_system_prompts_are_long_enough_to_cache() -> None:
    for key in bc.CONFIGS:
        meta = json.loads((bc.run_dir(DATE, key) / "run.json").read_text())
        cal = meta["calibration"]
        assert cal["drafter"]["system"] >= prices.MIN_CACHEABLE[meta["drafter_model"]]
        if "classifier" in cal:
            assert cal["classifier"]["system"] >= prices.MIN_CACHEABLE[prices.CLASSIFIER_MODEL]


def test_reply_check_tokens_measured_when_recorded() -> None:
    checked = {"reply_check": {"status": "checked", "input_tokens": 512}}
    assert prices.reply_check_tokens(checked) == 512
    assert prices.reply_check_tokens({"reply_check": {"status": "skipped: abstained"}}) == 0
    old_shown = {"draft_mode": "answer", "reply": "Hi", "abstain_reason": "", "problems": []}
    assert prices.reply_check_tokens(old_shown) == prices.REPLY_CHECK_TOKENS_EST
    assert prices.reply_check_tokens({**old_shown, "problems": ["x"]}) == 0


def test_doc_tables_are_the_script_output() -> None:
    for name, block in bc.blocks(DATE).items():
        assert bc.split(DOC, name)[1] == block, "run: python -m evals.business_case --update-doc"


def test_doc_headline_matches_the_script() -> None:
    headline = DOC.split("\n\n")[1].replace("\n", " ")
    rec = bc.config(DATE, bc.RECOMMENDED)
    per_ready = rec.threshold()
    # Rounded up: at the threshold the pilot does not lose money; a cent less, it does.
    assert rec.net(1.0, per_ready) >= 0 > rec.net(1.0, per_ready - 0.01)
    base = bc.COST_PER_CONTACT["base"]
    for figure in (
        f"${per_ready:.2f} of agent time",
        f"({per_ready / base:.0%} of a ${base:.0f}",
        f"about ${rec.model_month:.0f} a month",
        f"about ${bc.FIXED:,.0f}",
    ):
        assert figure in headline, figure


def test_recommendation_holds_in_the_run_shown() -> None:
    # "moves the total by less than a fifth. No configuration had a violation; ... the best
    # routing, a classifier as fast as the local Laya and over ten times faster than the LLM
    # classifier" (as fast: the same p50 at the table's 0.1 s).
    words = " ".join(DOC.split())
    for claim in (
        "moves the total by less than a fifth",
        "No configuration had a violation",
        "the best routing",
        "as fast as the local Laya and over ten times faster than the LLM classifier",
    ):
        assert claim in words, claim
    runs = {key: bc.config(DATE, key) for key in bc.CONFIGS}
    rec = runs[bc.RECOMMENDED]
    totals = [c.cost_month for c in runs.values()]
    assert max(totals) < min(totals) * 1.2
    for c in runs.values():
        assert c.metrics["violations"]["count"] == 0
        assert rec.metrics["route"]["accuracy"]["value"] >= c.metrics["route"]["accuracy"]["value"]
    classify = {k: c.metrics["latency_ms"]["classify"]["p50"] / 1000 for k, c in runs.items()}
    assert f"{classify[bc.RECOMMENDED]:.1f}" == f"{classify['laya+haiku']:.1f}"
    assert classify["llm+haiku"] > 10 * classify[bc.RECOMMENDED]


def test_doc_inputs_are_the_script_assumptions() -> None:
    assert len(set(prices.MIN_CACHEABLE.values())) == 1
    for text in (
        f"{bc.TICKETS_PER_MONTH:,}",
        f"{bc.CACHE_HIT:.0%} of calls hit the 5-minute cache",
        f"prompts of {prices.MIN_CACHEABLE[prices.CLASSIFIER_MODEL]}+ tokens cache",
        f"${bc.FIXED:,.0f} a month: VM ${bc.HOSTING:.0f}, an engineer {bc.ENGINEER_H} h a week "
        f"at ${bc.ENGINEER_RATE:.0f}, the support lead {bc.LEAD_H} h a week at "
        f"${bc.LEAD_RATE:.0f}, 52/12 weeks a month",
        f"${bc.LAYA_HOST:.0f} host",
        " / ".join(f"${v:.0f}" for v in bc.COST_PER_CONTACT.values()),
        " / ".join(f"{v:.0%}" for v in bc.TIME_SAVED_READY.values()),
    ):
        assert text in DOC, text

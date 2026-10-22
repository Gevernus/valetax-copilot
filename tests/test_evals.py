"""The scoring itself: saved runs keep their verdict when fixed texts or checks change."""

import hashlib
import json
from typing import Any

import pytest
from evals import metrics
from evals.run import RESULTS, load_labels
from evals.run_drafts import load_drafts

from copilot.kb import load_kb


def cards(run: str) -> list[dict[str, Any]]:
    path = RESULTS / run / "cards.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines()]


def test_committed_v3_run_rescores_with_no_violations() -> None:
    # These cards carry the first wording of the trading decline; it still counts as the decline.
    m = metrics.compute(load_labels(), cards("2026-10-22-v3/jev+haiku"), load_kb())
    assert m["violations"]["count"] == 0, m["violations"]["tickets"]


def test_a_scoring_error_counts_as_a_violation(monkeypatch: pytest.MonkeyPatch) -> None:
    def broken(*_: object) -> list[str]:
        raise KeyError("x")

    monkeypatch.setattr(metrics, "violations", broken)
    m = metrics.compute(load_labels(), cards("2026-10-22-v3/jev+haiku")[:2], load_kb())
    assert m["violations"]["count"] == 2


def test_drafts_holdout_is_frozen() -> None:
    # The reply checks are tuned on the dev split only. A changed holdout row needs a new split.
    holdout = [r for r in load_drafts() if r["split"] == "holdout"]
    digest = hashlib.sha256(json.dumps(holdout, ensure_ascii=False, sort_keys=True).encode())
    assert digest.hexdigest() == "c76ead634bace4b47c9069f1bd5fd3df0da2ba714b49c2ae1c97636554a68e1d"

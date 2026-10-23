"""The scoring itself: saved runs keep their verdict when fixed texts or checks change."""

import hashlib
import json
from typing import Any

import pytest
from evals import metrics
from evals.run import RESULTS, load_labels
from evals.run_drafts import SETS, load_drafts

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
    assert digest.hexdigest() == "8fd77a6cc93fcf29649bdccb3b013369d80cb24eccc67f46edf024578fd5fd93"


def test_drafts_challenge_set_is_frozen() -> None:
    # Written by a separate agent that never saw the checks; run once, never tuned on, and a
    # row that looks mislabelled is reported as a disagreement, not relabelled.
    digest = hashlib.sha256(SETS["drafts_challenge"].read_bytes()).hexdigest()
    assert digest == "5817ba50514466f4a2d1e455231f04f549a50a9a61f17d313b8016b1e186b9bc"


def test_figures_challenge_set_is_frozen() -> None:
    # Blind set for the number layer: run once, never tuned on or relabelled.
    digest = hashlib.sha256((RESULTS.parent / "figures_challenge.jsonl").read_bytes()).hexdigest()
    assert digest == "f248bcdcfda1e243ba6358901eef96e84c02c54a8ec2e5eaf72790e9b16d2d35"

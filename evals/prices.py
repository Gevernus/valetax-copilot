"""Official prices and the cost of one ticket: the one formula behind `evals.run report`
(warm and cold cache) and `evals.business_case` (an assumed live cache-hit share).

Sources, fetched 2026-10-23:
- Anthropic: platform.claude.com/docs/en/about-claude/pricing (Haiku 5.5 for prompts up to
  100k tokens; Sonnet 5.5 cache hits are 0.05x input). Minimum cacheable prefix 512 tokens on
  both: platform.claude.com/docs/en/build-with-claude/prompt-caching; shorter is not cached.
- TypeSafe: docs.typesafe.ai/models, jev-1.14.0 "$42 / $0.042" per Btok / Mtok input; "Output
  tokens are free".
"""

import statistics
from dataclasses import dataclass
from typing import Any, Final


@dataclass(frozen=True, slots=True)
class Price:
    """USD per million tokens."""

    input: float
    cache_write_5m: float
    cache_hit: float
    output: float


PRICES: Final = {
    "claude-haiku-5-5": Price(input=0.10, cache_write_5m=0.125, cache_hit=0.01, output=0.50),
    "claude-sonnet-5-5": Price(input=2.00, cache_write_5m=2.50, cache_hit=0.10, output=10.00),
}
MIN_CACHEABLE: Final = {"claude-haiku-5-5": 512, "claude-sonnet-5-5": 512}
CLASSIFIER_MODEL: Final = "claude-haiku-5-5"  # the LLM classifier backend
JEV_INPUT: Final = 0.042

# For runs made before the reply check recorded its tokens: its three questions are about half
# the request of the nine ticket questions (~1,180 Jev tokens measured), plus a short draft.
REPLY_CHECK_TOKENS_EST: Final = 600


def llm_call_cost(model: str, prefix: float, user: float, output: float, hit: float) -> float:
    """USD for one call. The system prompt is a cache hit with probability `hit` and a 5-minute
    cache write otherwise; below the model's minimum cacheable length it is plain input."""
    p = PRICES[model]
    if prefix >= MIN_CACHEABLE[model]:
        prefix_usd = prefix * (hit * p.cache_hit + (1 - hit) * p.cache_write_5m)
    else:
        prefix_usd = prefix * p.input
    return (prefix_usd + user * p.input + output * p.output) / 1e6


def user_tokens(card: dict[str, Any]) -> int:
    """The per-ticket message (mode, language, ticket) at 3 characters per token: conservative for
    English, close for Cyrillic and Arabic. The CLI reports it inside its own overhead."""
    return 20 + len(card["ticket"]) // 3


def reply_check_tokens(card: dict[str, Any]) -> float:
    """Jev input tokens of the reply check: as recorded by newer runs; for older runs, the
    estimate on a draft the check would have seen (answer mode, not abstained, passed the source
    check)."""
    record = card.get("reply_check")
    if record is not None:
        return float(record.get("input_tokens", 0)) if record.get("status") == "checked" else 0.0
    shown = (
        card.get("draft_mode") == "answer"
        and bool((card.get("reply") or "").strip())
        and not card.get("abstain_reason")
        and not card.get("problems")
    )
    return REPLY_CHECK_TOKENS_EST if shown else 0.0


@dataclass(frozen=True, slots=True)
class TicketCost:
    """Mean USD per ticket by stage."""

    classify: float
    draft: float
    reply_check: float

    @property
    def total(self) -> float:
        return self.classify + self.draft + self.reply_check


def _calls(card: dict[str, Any], stage: str) -> int:
    """Calls made at a stage; a card saved before attempts were recorded made one of each."""
    attempts = card.get("attempts")
    return 1 if attempts is None else int(attempts.get(stage, 0))


def run_cost(
    cards: list[dict[str, Any]], meta: dict[str, Any], hit_draft: float, hit_classify: float
) -> TicketCost:
    """Mean cost per ticket of a saved run. Our own tokens only: the calibrated system prompt
    (claude-cli) or the cached part the API reports, the ticket message, measured output tokens
    (they include adaptive thinking: an upper bound at low effort), Jev input tokens. A retried
    stage counts every attempt as paid, the failed ones at the cost of the one that answered: an
    upper bound, since a failed call reports no tokens. Failure cards count too (they are left
    out of quality, not of cost): a draft that failed is priced as its prompt, per attempt."""
    cal = meta.get("calibration", {})
    classify: list[float] = []
    draft: list[float] = []
    reply: list[float] = []
    for card in cards:
        cls = card["classifier"]
        if cls["backend"] == "jev":
            classify.append(cls["input_tokens"] * JEV_INPUT / 1e6 * _calls(card, "classify"))
        elif cls["backend"] == "llm":
            system = cal["classifier"]["system"]
            out = cls["output_tokens"]
            classify.append(
                llm_call_cost(CLASSIFIER_MODEL, system, user_tokens(card), out, hit_classify)
                * _calls(card, "classify")
            )
        else:
            classify.append(0.0)  # local model: no per-token cost
        d = card["drafter"]
        if d["model"]:
            system = cal.get("drafter", {}).get("system") or (
                d["cache_read_tokens"] + d["cache_write_tokens"]
            )
            out = d["output_tokens"]
            cost = llm_call_cost(d["model"], system, user_tokens(card), out, hit_draft)
            draft.append(cost * _calls(card, "draft"))
        else:
            draft.append(0.0)
        reply.append(reply_check_tokens(card) * JEV_INPUT / 1e6 * _calls(card, "reply_check"))
    mean = statistics.fmean
    return TicketCost(mean(classify), mean(draft), mean(reply))

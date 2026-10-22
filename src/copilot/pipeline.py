"""One ticket through the co-pilot: mask, rules, classify, draft, check, route."""

import time
from dataclasses import asdict, dataclass, field
from typing import Any

from copilot import rules
from copilot.classify import YES_NO, Classification, Classifier
from copilot.draft import PROMPT_VERSION, Draft, Drafter, Mode, trading_decline
from copilot.grounding import check_draft
from copilot.kb import KnowledgeBase
from copilot.language import detect_language
from copilot.llm import LlmError, LlmUsage
from copilot.masking import mask_pii
from copilot.routing import CONSEQUENCE, Reason, Signals, Thresholds, route


@dataclass(slots=True)
class Card:
    """What the support agent sees, and what the trace line is cut from."""

    ticket_id: str
    route: str
    reasons: list[str]
    consequences: list[str]
    category: str
    urgency: str
    sentiment: str
    language: str
    flags: dict[str, float]  # P(yes) per yes/no question
    rule_hits: list[str]
    reply: str | None  # None when withheld or abstained
    citations: list[dict[str, str]]
    unanswered: list[str]
    abstain_reason: str
    problems: list[str]  # grounding-check findings
    masked: dict[str, int]
    timings_ms: dict[str, int]
    classifier: dict[str, Any]
    drafter: dict[str, Any]
    kb_version: str
    prompt_version: str = PROMPT_VERSION
    draft_mode: str | None = None
    raw_reply: str | None = field(default=None, repr=False)  # kept for evals, never traced

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def trace(self) -> dict[str, Any]:
        """One observability line: decisions, versions, tokens and timings. No ticket text,
        no reply, no prompt."""
        return {
            "ticket_id": self.ticket_id,
            "route": self.route,
            "reasons": self.reasons,
            "category": self.category,
            "urgency": self.urgency,
            "language": self.language,
            "flags": self.flags,
            "rule_hits": self.rule_hits,
            "abstained": bool(self.abstain_reason),
            "draft_shown": self.reply is not None,
            "citations": [c["id"] for c in self.citations],
            "problems": len(self.problems),
            "masked": self.masked,
            "timings_ms": self.timings_ms,
            "classifier": self.classifier,
            "drafter": self.drafter,
            "kb_version": self.kb_version,
            "prompt_version": self.prompt_version,
        }


class Copilot:
    def __init__(
        self,
        kb: KnowledgeBase,
        classifier: Classifier,
        drafter: Drafter,
        thresholds: Thresholds | None = None,
    ) -> None:
        self.kb = kb
        self.classifier = classifier
        self.drafter = drafter
        self.thresholds = thresholds or Thresholds()

    def process(self, ticket_id: str, text: str) -> Card:
        timings: dict[str, int] = {}
        t = _Timer(timings)

        with t("mask"):
            masked = mask_pii(text)
            ticket = masked.text
            rule_hits = [
                name
                for name, hit in (
                    ("injection", rules.looks_like_injection(ticket)),
                    ("trading_advice", rules.asks_trading_advice(ticket)),
                )
                if hit
            ]
            language = detect_language(ticket)

        with t("classify"):
            cls = self.classifier.classify(ticket)

        th = self.thresholds
        a = cls.answers
        p_yes = {name: round(a[name].p_yes, 3) for name in sorted(YES_NO)}
        flagged = {
            "injection": "injection" in rule_hits or a["injection"].p_yes >= th.injection,
            "aml": a["aml_case"].p_yes >= th.aml_case,
            "kyc": a["kyc_case"].p_yes >= th.kyc_case,
            "complaint": a["complaint"].p_yes >= th.complaint,
            "trading_advice": "trading_advice" in rule_hits
            or a["trading_advice"].p_yes >= th.trading_advice,
            "account_lookup": a["account_lookup"].p_yes >= th.account_lookup,
        }
        low_confidence = a["category"].p < th.category_min

        draft: Draft | None = None
        draft_error = False
        llm_usage = LlmUsage()
        llm_latency = 0
        mode: Mode | None = None
        problems: tuple[str, ...] = ()
        if not flagged["injection"]:
            mode = (
                Mode.ACKNOWLEDGE
                if flagged["aml"] or flagged["kyc"] or flagged["complaint"]
                else Mode.ANSWER
            )
            with t("draft"):
                try:
                    result = self.drafter.draft(ticket, language, mode)
                    draft, llm_usage, llm_latency = (
                        result.draft,
                        result.llm.usage,
                        result.llm.latency_ms,
                    )
                except LlmError:
                    draft_error = True
            if draft is not None:
                with t("check"):
                    problems = check_draft(draft, self.kb, ticket, mode).problems

        cited = [c for c in (draft.citations if draft else []) if c in self.kb.sections]
        signals = Signals(
            injection=flagged["injection"],
            aml=flagged["aml"],
            kyc=flagged["kyc"],
            complaint=flagged["complaint"],
            trading_advice=flagged["trading_advice"],
            account_lookup=flagged["account_lookup"],
            low_confidence=low_confidence,
            abstained=bool(draft and draft.abstain),
            unanswered=bool(draft and not draft.abstain and draft.unanswered),
            cites_conflict=any(self.kb.has_conflict(c) for c in cited),
            grounding_failed=bool(problems),
            draft_error=draft_error,
        )
        decision = route(signals)

        reply: str | None = None
        if draft and not draft.abstain and not problems:
            reply = draft.reply.strip()
            if flagged["trading_advice"]:
                reply = f"{reply}\n\n{trading_decline(language)}".strip()
        elif flagged["trading_advice"] and not flagged["injection"] and not problems:
            # Nothing else to answer: the decline alone is the draft.
            reply = trading_decline(language)

        return Card(
            ticket_id=ticket_id,
            route=decision.label,
            reasons=[r.value for r in decision.reasons],
            consequences=[CONSEQUENCE[r] for r in decision.reasons],
            category=a["category"].choice,
            urgency=a["urgency"].choice,
            sentiment=a["sentiment"].choice,
            language=language,
            flags=p_yes,
            rule_hits=rule_hits,
            reply=reply,
            citations=[
                {"id": c, "title": self.kb.sections[c].title, "url": self.kb.sections[c].urls[0]}
                for c in cited
            ],
            unanswered=list(draft.unanswered) if draft else [],
            abstain_reason=draft.abstain_reason if draft and draft.abstain else "",
            problems=list(problems),
            masked=masked.counts,
            timings_ms=timings,
            classifier=_classifier_meta(cls),
            drafter={
                "model": self.drafter.model if mode else None,
                "latency_ms": llm_latency,
                **asdict(llm_usage),
            },
            kb_version=self.kb.version,
            draft_mode=mode.value if mode else None,
            raw_reply=draft.reply if draft else None,
        )


def _classifier_meta(cls: Classification) -> dict[str, Any]:
    return {
        "backend": cls.backend,
        "model": cls.model,
        "category_p": round(cls.answers["category"].p, 3),
        **asdict(cls.usage),
    }


class _Timer:
    def __init__(self, sink: dict[str, int]) -> None:
        self._sink = sink
        self._name = ""
        self._start = 0.0

    def __call__(self, name: str) -> "_Timer":
        self._name = name
        return self

    def __enter__(self) -> None:
        self._start = time.perf_counter()

    def __exit__(self, *exc: object) -> None:
        self._sink[self._name] = int((time.perf_counter() - self._start) * 1000)


__all__ = ["Card", "Copilot", "Reason"]

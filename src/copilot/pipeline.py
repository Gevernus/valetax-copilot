"""One ticket through the co-pilot: mask, rules, classify, draft, check, route."""

import time
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any

from pydantic import ValidationError

from copilot import rules
from copilot.classify import YES_NO, Classification, Classifier
from copilot.classify.questions import REPLY, TICKET
from copilot.draft import PROMPT_VERSION, Draft, Drafter, acknowledgement, trading_decline
from copilot.grounding import check_draft
from copilot.kb import KnowledgeBase
from copilot.language import detect_language
from copilot.llm import LlmError, LlmUsage
from copilot.masking import mask_pii
from copilot.reply_guard import check_reply
from copilot.routing import CONSEQUENCE, Reason, Signals, Thresholds, route


class Mode(StrEnum):
    ANSWER = "answer"  # the drafter answers from the KB
    ACKNOWLEDGE = "acknowledge"  # complaint, KYC or AML case: the fixed acknowledgement only


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
    client_figures: list[str]  # in the draft and the client's message, not in the sources
    masked: dict[str, int]
    timings_ms: dict[str, int]
    classifier: dict[str, Any]
    drafter: dict[str, Any]
    kb_version: str
    prompt_version: str = PROMPT_VERSION
    reply_check: dict[str, Any] = field(default_factory=dict)  # P(yes) per reply question
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
            "client_figures": len(self.client_figures),
            "masked": self.masked,
            "timings_ms": self.timings_ms,
            "classifier": self.classifier,
            "drafter": self.drafter,
            "reply_check": self.reply_check,
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
        *,
        reply_checker: Classifier | None,
    ) -> None:
        """`reply_checker` asks the REPLY questions of each shown draft; None is a deliberate
        choice (patterns only), recorded in every trace line."""
        if classifier.questions is not TICKET:
            raise ValueError("the ticket classifier must answer the TICKET questions")
        if reply_checker is not None and reply_checker.questions is not REPLY:
            raise ValueError("the reply checker must answer the REPLY questions")
        self.kb = kb
        self.classifier = classifier
        self.drafter = drafter
        self.thresholds = thresholds or Thresholds()
        self.reply_checker = reply_checker

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
        reserved = next((case for case in ("aml", "kyc", "complaint") if flagged[case]), None)
        problems: tuple[str, ...] = ()
        client_figures: tuple[str, ...] = ()
        check_error = False
        reply_problems: tuple[str, ...] = ()
        reply_reasons: frozenset[Reason] = frozenset()
        reply_check: dict[str, Any] = {"status": "not run"}
        if not flagged["injection"]:
            # A reserved case gets the fixed acknowledgement below; the model writes nothing.
            mode = Mode.ACKNOWLEDGE if reserved else Mode.ANSWER
        if mode is Mode.ANSWER:
            with t("draft"):
                try:
                    result = self.drafter.draft(ticket, language)
                    draft, llm_usage, llm_latency = (
                        result.draft,
                        result.llm.usage,
                        result.llm.latency_ms,
                    )
                except (LlmError, ValidationError):
                    draft_error = True
            if draft is not None and not draft.abstain and not draft.reply.strip():
                # Saying nothing is abstaining, whatever the flag says.
                draft = draft.model_copy(update={"abstain": True, "abstain_reason": "empty reply"})
            if draft is not None:
                with t("check"):
                    try:
                        check = check_draft(draft, self.kb, ticket)
                        problems = check.problems
                        # Only a shown draft needs its client figures checked.
                        client_figures = () if problems else check.client_figures
                        if draft.abstain:
                            reply_check = {"status": "skipped: abstained"}
                        else:
                            # Patterns on every draft, so the reason is not lost; the model
                            # only on a draft that could still be shown.
                            checker = None if problems else self.reply_checker
                            guard = check_reply(draft.reply, checker, self.thresholds.reply_flag)
                            reply_problems, reply_reasons = guard.problems, guard.reasons
                            reply_check = guard.record
                            if problems and self.reply_checker is not None:
                                reply_check = {"status": "skipped: grounding"}
                            if reply_problems:
                                client_figures = ()
                    except Exception:  # noqa: BLE001 - a check that cannot run must withhold, not crash
                        check_error = True
                        reply_check = {"status": "error"}

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
            tipping_off=Reason.TIPPING_OFF in reply_reasons,
            reserved_wording=Reason.RESERVED_WORDING in reply_reasons,
            client_figures=bool(client_figures),
            grounding_failed=bool(problems),
            check_error=check_error,
            draft_error=draft_error,
        )
        decision = route(signals)

        parts: list[str] = []
        if mode is Mode.ACKNOWLEDGE and reserved:
            parts.append(acknowledgement(reserved, language))
        elif draft and not draft.abstain and not (problems or reply_problems or check_error):
            parts.append(draft.reply.strip())
        if flagged["trading_advice"] and mode:
            # Written by code, so it stands even when the model's part is withheld.
            parts.append(trading_decline(language))
        reply = "\n\n".join(parts) if parts else None

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
            problems=[*problems, *reply_problems],
            client_figures=list(client_figures),
            masked=masked.counts,
            timings_ms=timings,
            classifier=_classifier_meta(cls),
            drafter={
                "model": self.drafter.model if mode is Mode.ANSWER else None,
                "latency_ms": llm_latency,
                **asdict(llm_usage),
            },
            kb_version=self.kb.version,
            reply_check=reply_check,
            draft_mode=mode.value if mode else None,
            raw_reply=draft.reply if draft else None,
        )


def _classifier_meta(cls: Classification) -> dict[str, Any]:
    return {
        "questions_version": TICKET.version,
        "prompt_version": cls.prompt_version or None,
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

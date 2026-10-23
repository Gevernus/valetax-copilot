"""One ticket through the co-pilot: mask, rules, classify, draft, check, route."""

import hashlib
import time
from dataclasses import asdict, dataclass, field, replace
from enum import StrEnum
from pathlib import Path
from typing import Any

from copilot import grounding, quantities, reply_guard, routing, rules
from copilot.classify import YES_NO, Classification, Classifier, Usage
from copilot.classify.questions import REPLY, TICKET
from copilot.draft import PROMPT_VERSION, Draft, Drafter, acknowledgement, trading_decline
from copilot.errors import Budget, ProviderError, RetryPolicy, UsageLimitError
from copilot.grounding import check_draft
from copilot.kb import KnowledgeBase
from copilot.language import detect_language
from copilot.llm import LlmUsage
from copilot.masking import mask_pii
from copilot.normalise import normalise
from copilot.reply_guard import check_reply
from copilot.routing import CONSEQUENCE, Reason, Signals, Thresholds, route

# Longer than any support message we expect, counted on the normalised text: the linear code
# rules (masking, injection and advice patterns) still read it, the models do not. Raw input
# beyond MAX_RAW_CHARS is not read at all. There is no ingest queue in this repo; the caps
# protect whatever feeds the co-pilot later.
MAX_TICKET_CHARS = 20_000
MAX_RAW_CHARS = 4 * MAX_TICKET_CHARS
# Card fields the agent's export never carries: the model's raw reply.
EVAL_ONLY = ("raw_reply",)


def agent_view(card: dict[str, Any]) -> dict[str, Any]:
    """What the agent may see of a card (as a dict, saved or fresh): never the raw reply, and
    none of the model's other text (unanswered questions, abstain reason) when its draft was
    withheld. Cards saved before `withheld` existed count as withheld when they have problems
    or a raw reply that was not shown."""
    out = {k: v for k, v in card.items() if k not in EVAL_ONLY}
    withheld = card.get("withheld")
    if withheld is None:
        withheld = bool(card.get("problems")) or (
            card.get("reply") is None and bool(card.get("raw_reply"))
        )
    if withheld:
        out["unanswered"] = []
        out["abstain_reason"] = ""
    return out


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
    flags: dict[str, float | None]  # P(yes) per yes/no question; None on a failure card
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
    attempts: dict[str, int] = field(default_factory=dict)  # calls per stage, retries included
    error: dict[str, Any] | None = None  # stage, error class and attempts when a stage failed
    versions: dict[str, Any] = field(default_factory=dict)
    withheld: bool = False  # the model wrote a draft that a check kept from the agent
    ticket: str = ""  # the masked, normalised text the models saw; never in the trace
    raw_reply: str | None = field(default=None, repr=False)  # the model's text, withheld or not

    def to_dict(self) -> dict[str, Any]:
        """What the agent sees: `agent_view` of the card."""
        return agent_view(asdict(self))

    def to_eval_dict(self) -> dict[str, Any]:
        """For evals and debugging only: every field, model text included."""
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
            "attempts": self.attempts,
            "error": self.error,
            "versions": self.versions,
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
        retry: RetryPolicy | None = None,
        raise_usage_limit: bool = False,
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
        self.retry = retry or RetryPolicy()
        # Evals stop on a usage limit instead of scoring it; for the agent it is a failed ticket.
        self.raise_usage_limit = raise_usage_limit
        self.versions = {
            "prompt": PROMPT_VERSION,
            "kb": kb.version,
            "ticket_questions": TICKET.version,
            "reply_questions": REPLY.version,
            "rules": _RULES_VERSION,
            "thresholds": asdict(self.thresholds),
        }

    def process(self, ticket_id: str, text: str) -> Card:
        """One ticket to one card. Any failure ends as a card for a person, never an exception,
        except a usage limit, which stops the caller instead of being recorded as a result."""
        run = _Run(Budget(self.retry))
        try:
            return self._process(ticket_id, text, run)
        except UsageLimitError as e:
            if self.raise_usage_limit:
                raise
            return self._failure_card(ticket_id, run, self._failed(run), e)
        except Exception as e:  # noqa: BLE001 - whatever failed, a person handles the ticket
            return self._failure_card(ticket_id, run, self._failed(run), e)

    def _process(self, ticket_id: str, text: str, run: "_Run") -> Card:
        t = _Timer(run)

        with t("mask"):
            if len(text) > MAX_RAW_CHARS:
                return self._failure_card(ticket_id, run, Signals(too_long=True), None)
            # The only form of the text from here on: cap, masking, rules, models, check, card.
            normalised = normalise(text)
            if len(normalised) > MAX_RAW_CHARS:  # NFKC can expand a short input
                return self._failure_card(ticket_id, run, Signals(too_long=True), None)
            masked = mask_pii(normalised)
            ticket = run.ticket = masked.text
            rule_hits = run.rule_hits = [
                name
                for name, hit in (
                    ("injection", rules.looks_like_injection(ticket)),
                    ("trading_advice", rules.asks_trading_advice(ticket)),
                )
                if hit
            ]
            if len(ticket) > MAX_TICKET_CHARS:
                return self._failure_card(
                    ticket_id, run, Signals(too_long=True), None, masked=masked.counts
                )
            language = detect_language(ticket)

        with t("classify"):
            cls = run.budget.call(
                "classify", lambda timeout: self.classifier.classify(ticket, timeout_s=timeout)
            )

        th = self.thresholds
        a = cls.answers
        p_yes: dict[str, float | None] = {name: round(a[name].p_yes, 3) for name in sorted(YES_NO)}
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
        error: dict[str, Any] | None = None  # a provider or check failure: kept out of quality
        reply_problems: tuple[str, ...] = ()
        reply_reasons: frozenset[Reason] = frozenset()
        reply_check: dict[str, Any] = {"status": "not run"}
        if not flagged["injection"]:
            # A reserved case gets the fixed acknowledgement below; the model writes nothing.
            mode = Mode.ACKNOWLEDGE if reserved else Mode.ANSWER
        if mode is Mode.ANSWER:
            with t("draft"):
                try:
                    result = run.budget.call(
                        "draft",
                        lambda timeout: self.drafter.draft(ticket, language, timeout_s=timeout),
                    )
                    draft, llm_usage, llm_latency = (
                        result.draft,
                        result.llm.usage,
                        result.llm.latency_ms,
                    )
                except UsageLimitError:
                    raise
                except ProviderError as e:
                    draft_error = True
                    error = run.error_record(e)
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
                            if checker is not None:
                                checker = _Retrying(checker, run.budget)
                            guard = check_reply(draft.reply, checker, self.thresholds.reply_flag)
                            reply_problems, reply_reasons = guard.problems, guard.reasons
                            reply_check = guard.record
                            if problems and self.reply_checker is not None:
                                reply_check = {"status": "skipped: grounding"}
                        # The model's other text reaches the agent too: the same patterns.
                        side = check_reply(
                            "\n".join([*draft.unanswered, draft.abstain_reason]), None, 1.0
                        )
                        reply_problems = (*reply_problems, *side.problems)
                        reply_reasons = reply_reasons | side.reasons
                        if reply_problems:
                            client_figures = ()
                    except UsageLimitError:
                        raise
                    except Exception as e:  # noqa: BLE001 - a check that cannot run must withhold
                        check_error = True
                        reply_check = {"status": "error"}
                        if isinstance(e, ProviderError):  # an outage, kept out of quality;
                            error = run.error_record(e)  # a bug in our own check is scored
        withheld = draft is not None and bool(problems or reply_problems or check_error)

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
            # A withheld draft's unanswered list is not shown, so it cannot be "filled in".
            unanswered=bool(draft and not draft.abstain and draft.unanswered and not withheld),
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
        elif draft and not draft.abstain and not withheld:
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
            timings_ms=run.timings,
            classifier=_classifier_meta(cls),
            drafter={
                "model": self.drafter.model if mode is Mode.ANSWER else None,
                "latency_ms": llm_latency,
                **asdict(llm_usage),
            },
            kb_version=self.kb.version,
            reply_check=reply_check,
            attempts=dict(run.budget.attempts),
            versions=self.versions,
            withheld=withheld,
            error=error,
            ticket=ticket,
            draft_mode=mode.value if mode else None,
            raw_reply=draft.reply if draft else None,
        )

    @staticmethod
    def _failed(run: "_Run") -> Signals:
        if run.stage == "classify":
            return Signals(classifier_error=True)
        return Signals(pipeline_error=True)

    def _failure_card(
        self,
        ticket_id: str,
        run: "_Run",
        signals: Signals,
        error: Exception | None,
        masked: dict[str, int] | None = None,
    ) -> Card:
        """A card for a person, shaped like any other card: no draft, nothing from a model; its
        reasons come from the routing table like every other card's. In the trace the stage and
        the error class only (never the message, which can carry a response body)."""
        # What the rules already found stays on the card: an injection ticket whose classifier
        # failed still says prompt_injection.
        signals = replace(
            signals,
            injection=signals.injection or "injection" in run.rule_hits,
            trading_advice=signals.trading_advice or "trading_advice" in run.rule_hits,
        )
        decision = route(signals)
        record = (
            run.error_record(error)
            if error
            else {"stage": run.stage, "type": decision.reasons[0].value, "attempts": 0}
        )
        return Card(
            ticket_id=ticket_id,
            route=decision.label,
            reasons=[r.value for r in decision.reasons],
            consequences=[CONSEQUENCE[r] for r in decision.reasons],
            category="", urgency="", sentiment="", language="",
            flags=dict.fromkeys(sorted(YES_NO)), rule_hits=list(run.rule_hits), reply=None,
            citations=[], unanswered=[], abstain_reason="", problems=[], client_figures=[],
            masked=masked or {}, timings_ms=run.timings,
            classifier={"questions_version": TICKET.version, "prompt_version": None,
                        "backend": self.classifier.name, "model": None, "category_p": None,
                        **asdict(Usage())},
            drafter={"model": None, "latency_ms": 0, **asdict(LlmUsage())},
            kb_version=self.kb.version, attempts=dict(run.budget.attempts),
            versions=self.versions, error=record, ticket=run.ticket,
        )  # fmt: skip


class _Run:
    """What one ticket's processing has done so far: for the trace, and for the failure card."""

    def __init__(self, budget: Budget) -> None:
        self.budget = budget
        self.stage = "start"
        self.timings: dict[str, int] = {}
        self.ticket = ""  # normalised and masked, once masking has run
        self.rule_hits: list[str] = []

    def error_record(self, error: Exception) -> dict[str, Any]:
        """The failed stage, the error class and the calls made: nothing from the message."""
        stage = (
            "reply_check"
            if self.stage == "check" and "reply_check" in self.budget.attempts
            else self.stage
        )
        return {"stage": stage, "type": type(error).__name__,
                "attempts": self.budget.attempts.get(stage, 0)}  # fmt: skip


class _Retrying:
    """A classifier whose calls share the ticket's budget: time left as the timeout, retried
    when transient."""

    def __init__(self, inner: Classifier, budget: Budget) -> None:
        self.name, self.questions = inner.name, inner.questions
        self._inner, self._budget = inner, budget

    def classify(self, text: str, timeout_s: float | None = None) -> Classification:
        return self._budget.call(
            "reply_check", lambda timeout: self._inner.classify(text, timeout_s=timeout)
        )


def _rules_version() -> str:
    """The deterministic checks' and the routing table's source, hashed: any edit to these files,
    a comment included, is a new version."""
    digest = hashlib.sha256()
    for module in (rules, quantities, grounding, reply_guard, routing):
        digest.update(Path(str(module.__file__)).read_bytes())
    return digest.hexdigest()[:12]


_RULES_VERSION = _rules_version()


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
    def __init__(self, run: _Run) -> None:
        self._run = run
        self._start = 0.0

    def __call__(self, name: str) -> "_Timer":
        self._run.stage = name
        return self

    def __enter__(self) -> None:
        self._start = time.perf_counter()

    def __exit__(self, *exc: object) -> None:
        self._run.timings[self._run.stage] = int((time.perf_counter() - self._start) * 1000)


__all__ = ["Card", "Copilot", "Reason"]

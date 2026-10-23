"""One ticket through the co-pilot: mask, rules, classify, draft, check, route.

`Copilot.process` is the only entry point and never raises for a ticket: any failure becomes a
card for a person (a usage limit is re-raised only when evals ask). Every stage reads one text,
normalised and masked; the models never see the raw ticket and the trace never sees any text.
"""

import hashlib
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

from copilot import grounding, quantities, reply_guard, routing, rules
from copilot.classify import YES_NO, Answer, Classification, Classifier, Usage
from copilot.classify.questions import REPLY, TICKET
from copilot.draft import PROMPT_VERSION, Draft, Drafter, acknowledgement, trading_decline
from copilot.errors import Budget, ProviderError, RetryPolicy, UsageLimitError
from copilot.grounding import check_draft
from copilot.kb import KnowledgeBase
from copilot.language import detect_language
from copilot.llm import LlmUsage
from copilot.masking import Masked, mask_pii
from copilot.normalise import normalise
from copilot.reply_guard import check_reply
from copilot.routing import CONSEQUENCE, Reason, Thresholds, label, route

# Longer than any support message we expect, counted on the normalised text: the linear code
# rules (masking, injection and advice patterns) still read it, the models do not. Raw input
# beyond MAX_RAW_CHARS is not read at all.
MAX_TICKET_CHARS = 20_000
MAX_RAW_CHARS = 4 * MAX_TICKET_CHARS
# Card fields the agent's export never carries: the model's raw reply.
EVAL_ONLY = ("raw_reply",)
_RESERVED = (Reason.AML, Reason.KYC, Reason.COMPLAINT)  # acknowledged by code, decided by a person
_WITHHOLD = {
    Reason.GROUNDING_FAILED,
    Reason.TIPPING_OFF,
    Reason.RESERVED_WORDING,
    Reason.CHECK_ERROR,
}


def agent_view(card: dict[str, Any]) -> dict[str, Any]:
    """What the agent may see of a card, saved or fresh.

    Never the raw reply, and none of the model's other text (unanswered questions, abstain reason)
    when its draft was withheld. Cards saved before `withheld` existed count as withheld when they
    have problems or a raw reply that was not shown.
    """
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
    """Who writes the draft."""

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
    versions: dict[str, Any]  # prompt, KB, questions, rules and thresholds
    reply_check: dict[str, Any] = field(default_factory=dict)  # P(yes) per reply question
    draft_mode: str | None = None
    attempts: dict[str, int] = field(default_factory=dict)  # calls per stage, retries included
    error: dict[str, Any] | None = None  # stage, error class and attempts when a stage failed
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
        """One observability line: decisions, versions, tokens and timings.

        No ticket text, no reply, no prompt.
        """
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


@dataclass(slots=True)
class _Checked:
    """The drafter's answer and what the checks found in it."""

    draft: Draft | None = None
    usage: LlmUsage = field(default_factory=LlmUsage)
    latency_ms: int = 0
    reasons: set[Reason] = field(default_factory=set)  # from the draft and its checks
    problems: list[str] = field(default_factory=list)
    client_figures: tuple[str, ...] = ()
    reply_check: dict[str, Any] = field(default_factory=lambda: {"status": "not run"})
    error: dict[str, Any] | None = None  # a provider failure: kept out of quality

    @property
    def withheld(self) -> bool:
        """The model wrote a draft and a check kept it from the agent."""
        return self.draft is not None and bool(self.reasons & _WITHHOLD)


class Copilot:
    """The pipeline with its models; one instance serves many tickets."""

    def __init__(
        self,
        kb: KnowledgeBase,
        classifier: Classifier,
        drafter: Drafter,
        *,
        reply_checker: Classifier | None,
        retry: RetryPolicy | None = None,
        raise_usage_limit: bool = False,
    ) -> None:
        """Wire the pipeline to its models.

        `reply_checker` asks the REPLY questions of each shown draft; None is a deliberate choice
        (patterns only), recorded in every trace line. Evals set `raise_usage_limit` to stop on a
        usage limit instead of scoring it.
        """
        if classifier.questions is not TICKET:
            raise ValueError("the ticket classifier must answer the TICKET questions")
        if reply_checker is not None and reply_checker.questions is not REPLY:
            raise ValueError("the reply checker must answer the REPLY questions")
        self.kb = kb
        self.classifier = classifier
        self.drafter = drafter
        self.thresholds = Thresholds()
        self.reply_checker = reply_checker
        self.retry = retry or RetryPolicy()
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
        """One ticket to one card.

        Any failure ends as a card for a person, never an exception, except a usage limit when
        `raise_usage_limit` is set.
        """
        run = _Run(Budget(self.retry))
        try:
            return self._process(ticket_id, text, run)
        except UsageLimitError as e:
            if self.raise_usage_limit:
                raise
            return self._failure_card(ticket_id, run, run.failure_reason(), e)
        except Exception as e:  # noqa: BLE001 - any failure goes to a person
            return self._failure_card(ticket_id, run, run.failure_reason(), e)

    def _process(self, ticket_id: str, text: str, run: "_Run") -> Card:
        with run.stage("mask"):
            masked = _read(text, run)
            if masked is None or len(masked.text) > MAX_TICKET_CHARS:
                counts = masked.counts if masked else None
                return self._failure_card(ticket_id, run, Reason.TOO_LONG, None, counts)
            ticket = masked.text
            language = detect_language(ticket)
        with run.stage("classify"):
            cls = run.budget.call(
                "classify", lambda timeout: self.classifier.classify(ticket, timeout_s=timeout)
            )
        cases = self._cases(cls.answers, run.rule_hits)
        reserved = next((r for r in _RESERVED if r in cases), None)
        mode = None  # an injection gets no draft at all
        if Reason.PROMPT_INJECTION not in cases:
            mode = Mode.ACKNOWLEDGE if reserved else Mode.ANSWER
        checked = self._draft(ticket, language, run) if mode is Mode.ANSWER else _Checked()
        draft = checked.draft
        cited = [c for c in (draft.citations if draft else []) if c in self.kb.sections]
        if any(self.kb.has_conflict(c) for c in cited):
            checked.reasons.add(Reason.KB_CONFLICT)
        reasons = route(cases | checked.reasons)

        parts: list[str] = []
        if mode is Mode.ACKNOWLEDGE and reserved:
            parts.append(acknowledgement(reserved.value, language))
        elif draft and not draft.abstain and not checked.withheld:
            parts.append(draft.reply.strip())
        if Reason.TRADING_ADVICE in cases and mode:
            parts.append(trading_decline(language))  # by code: it stands when the draft does not

        return Card(
            ticket_id=ticket_id,
            route=label(reasons),
            reasons=[r.value for r in reasons],
            consequences=[CONSEQUENCE[r] for r in reasons],
            category=cls.answers["category"].choice,
            urgency=cls.answers["urgency"].choice,
            sentiment=cls.answers["sentiment"].choice,
            language=language,
            flags={name: round(cls.answers[name].p_yes, 3) for name in sorted(YES_NO)},
            rule_hits=run.rule_hits,
            reply="\n\n".join(parts) if parts else None,
            citations=[
                {"id": c, "title": self.kb.sections[c].title, "url": self.kb.sections[c].urls[0]}
                for c in cited
            ],
            unanswered=list(draft.unanswered) if draft else [],
            abstain_reason=draft.abstain_reason if draft and draft.abstain else "",
            problems=checked.problems,
            client_figures=list(checked.client_figures),
            masked=masked.counts,
            timings_ms=run.timings,
            classifier=_classifier_meta(cls, self.classifier.name),
            drafter={
                "model": self.drafter.model if mode is Mode.ANSWER else None,
                "latency_ms": checked.latency_ms,
                **asdict(checked.usage),
            },
            versions=self.versions,
            reply_check=checked.reply_check,
            draft_mode=mode.value if mode else None,
            attempts=dict(run.budget.attempts),
            error=checked.error,
            withheld=checked.withheld,
            ticket=ticket,
            raw_reply=draft.reply if draft else None,
        )

    def _cases(self, a: dict[str, Answer], rule_hits: list[str]) -> set[Reason]:
        """The reasons the ticket itself gives: the input rules, and each flag at its threshold."""
        th = self.thresholds
        flagged = {
            Reason.PROMPT_INJECTION: "injection" in rule_hits
            or a["injection"].p_yes >= th.injection,
            Reason.AML: a["aml_case"].p_yes >= th.aml_case,
            Reason.KYC: a["kyc_case"].p_yes >= th.kyc_case,
            Reason.COMPLAINT: a["complaint"].p_yes >= th.complaint,
            Reason.TRADING_ADVICE: "trading_advice" in rule_hits
            or a["trading_advice"].p_yes >= th.trading_advice,
            Reason.ACCOUNT_LOOKUP: a["account_lookup"].p_yes >= th.account_lookup,
            Reason.LOW_CONFIDENCE: a["category"].p < th.category_min,
        }
        return {reason for reason, hit in flagged.items() if hit}

    def _draft(self, ticket: str, language: str, run: "_Run") -> _Checked:
        """Draft from the KB, then check the draft. A provider failure is a reason, not a raise."""
        out = _Checked()
        with run.stage("draft"):
            try:
                result = run.budget.call(
                    "draft", lambda timeout: self.drafter.draft(ticket, language, timeout_s=timeout)
                )
            except UsageLimitError:
                raise
            except ProviderError as e:
                out.reasons.add(Reason.DRAFT_ERROR)
                out.error = run.error_record(e)
                return out
        draft = result.draft
        if not draft.abstain and not draft.reply.strip():  # saying nothing is abstaining
            draft = draft.model_copy(update={"abstain": True, "abstain_reason": "empty reply"})
        out.draft, out.usage, out.latency_ms = draft, result.llm.usage, result.llm.latency_ms
        if draft.abstain:
            out.reasons.add(Reason.KB_GAP)
        with run.stage("check"):
            try:
                self._check(draft, ticket, run, out)
            except UsageLimitError:
                raise
            except Exception as e:  # noqa: BLE001 - a check that cannot run withholds
                out.reasons.add(Reason.CHECK_ERROR)
                out.reply_check = {"status": "error"}
                if isinstance(e, ProviderError):  # an outage, kept out of quality;
                    out.error = run.error_record(e)  # a bug in our own check is scored
        if out.client_figures:
            out.reasons.add(Reason.CLIENT_FIGURES)
        if draft.unanswered and not draft.abstain and not out.withheld:
            out.reasons.add(Reason.KB_GAP)  # a withheld draft's list is not shown to fill in
        return out

    def _check(self, draft: Draft, ticket: str, run: "_Run", out: _Checked) -> None:
        """The source check, then what the reply must not say.

        Patterns run on every draft; the REPLY questions only on a draft that could still be shown.
        """
        check = check_draft(draft, self.kb, ticket)
        problems = list(check.problems)
        if problems:
            out.reasons.add(Reason.GROUNDING_FAILED)
        else:
            out.client_figures = check.client_figures
        guards = []
        if draft.abstain:
            out.reply_check = {"status": "skipped: abstained"}
        else:
            checker = None if problems else self.reply_checker
            if checker is not None:
                checker = _Retrying(checker, run.budget)
            guard = check_reply(draft.reply, checker, self.thresholds.reply_flag)
            out.reply_check = guard.record
            if problems and self.reply_checker is not None:
                out.reply_check = {"status": "skipped: grounding"}
            guards.append(guard)
        # The model's other text reaches the agent too: the same patterns.
        guards.append(check_reply("\n".join([*draft.unanswered, draft.abstain_reason]), None, 1.0))
        for guard in guards:
            problems += guard.problems
            out.reasons |= guard.reasons
        if any(g.problems for g in guards):
            out.client_figures = ()
        out.problems = problems

    def _failure_card(
        self,
        ticket_id: str,
        run: "_Run",
        reason: Reason,
        error: Exception | None,
        masked: dict[str, int] | None = None,
    ) -> Card:
        """A card for a person, shaped like any other: no draft, nothing from a model.

        The rules' findings are kept. The trace gets the stage and the error class, never the
        message, which can carry a response body.
        """
        hits = {"injection": Reason.PROMPT_INJECTION, "trading_advice": Reason.TRADING_ADVICE}
        reasons = route({reason, *(hits[h] for h in run.rule_hits)})
        record = (
            run.error_record(error)
            if error
            else {"stage": run.stage_name, "type": reasons[0].value, "attempts": 0}
        )
        return Card(
            ticket_id=ticket_id, route=label(reasons), reasons=[r.value for r in reasons],
            consequences=[CONSEQUENCE[r] for r in reasons],
            category="", urgency="", sentiment="", language="",
            flags=dict.fromkeys(sorted(YES_NO)), rule_hits=list(run.rule_hits), reply=None,
            citations=[], unanswered=[], abstain_reason="", problems=[], client_figures=[],
            masked=masked or {}, timings_ms=run.timings,
            classifier=_classifier_meta(None, self.classifier.name),
            drafter={"model": None, "latency_ms": 0, **asdict(LlmUsage())},
            versions=self.versions, attempts=dict(run.budget.attempts), error=record,
            ticket=run.ticket,
        )  # fmt: skip


def _read(text: str, run: "_Run") -> Masked | None:
    """The one text every later stage reads: normalised, masked, with the input rules' hits.

    None when the raw or the normalised text is beyond MAX_RAW_CHARS (NFKC can expand it).
    """
    if len(text) > MAX_RAW_CHARS:
        return None
    normalised = normalise(text)
    if len(normalised) > MAX_RAW_CHARS:
        return None
    masked = mask_pii(normalised)
    run.ticket = masked.text
    run.rule_hits = [
        name
        for name, hit in (
            ("injection", rules.looks_like_injection(masked.text)),
            ("trading_advice", rules.asks_trading_advice(masked.text)),
        )
        if hit
    ]
    return masked


class _Run:
    """What one ticket's processing has done so far: for the trace, and for the failure card."""

    def __init__(self, budget: Budget) -> None:
        self.budget = budget
        self.stage_name = "start"
        self.timings: dict[str, int] = {}
        self.ticket = ""  # normalised and masked, once masking has run
        self.rule_hits: list[str] = []

    @contextmanager
    def stage(self, name: str) -> Iterator[None]:
        """Time a stage; a failure inside it is attributed to it."""
        self.stage_name = name
        started = time.perf_counter()
        try:
            yield
        finally:
            self.timings[name] = int((time.perf_counter() - started) * 1000)

    def failure_reason(self) -> Reason:
        """A failed classification is `classifier_error`; anything else `pipeline_error`."""
        if self.stage_name == "classify":
            return Reason.CLASSIFIER_ERROR
        return Reason.PIPELINE_ERROR

    def error_record(self, error: Exception) -> dict[str, Any]:
        """The failed stage, the error class and the calls made: nothing from the message."""
        stage = (
            "reply_check"
            if self.stage_name == "check" and "reply_check" in self.budget.attempts
            else self.stage_name
        )
        return {"stage": stage, "type": type(error).__name__,
                "attempts": self.budget.attempts.get(stage, 0)}  # fmt: skip


class _Retrying:
    """A classifier whose calls share the ticket's budget, retried when transient."""

    def __init__(self, inner: Classifier, budget: Budget) -> None:
        self.name, self.questions = inner.name, inner.questions
        self._inner, self._budget = inner, budget

    def classify(self, text: str, timeout_s: float | None = None) -> Classification:
        return self._budget.call(
            "reply_check", lambda timeout: self._inner.classify(text, timeout_s=timeout)
        )


def _rules_version() -> str:
    """A hash of the deterministic checks' and the routing table's source.

    Any edit to these files, a comment included, is a new version.
    """
    digest = hashlib.sha256()
    for module in (rules, quantities, grounding, reply_guard, routing):
        digest.update(Path(str(module.__file__)).read_bytes())
    return digest.hexdigest()[:12]


_RULES_VERSION = _rules_version()


def _classifier_meta(cls: Classification | None, backend: str) -> dict[str, Any]:
    if cls is None:  # the classification failed
        return {"questions_version": TICKET.version, "prompt_version": None, "backend": backend,
                "model": None, "category_p": None, **asdict(Usage())}  # fmt: skip
    return {
        "questions_version": TICKET.version,
        "prompt_version": cls.prompt_version or None,
        "backend": cls.backend,
        "model": cls.model,
        "category_p": round(cls.answers["category"].p, 3),
        **asdict(cls.usage),
    }


__all__ = ["Card", "Copilot", "Reason"]

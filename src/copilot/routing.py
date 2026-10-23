"""Routing rules: a table from signals to reasons. Any reason sends the ticket to a person."""

from dataclasses import dataclass, field
from enum import StrEnum


class Reason(StrEnum):
    TOO_LONG = "too_long"
    CLASSIFIER_ERROR = "classifier_error"
    PIPELINE_ERROR = "pipeline_error"
    PROMPT_INJECTION = "prompt_injection"
    AML = "aml"
    KYC = "kyc"
    COMPLAINT = "complaint"
    TRADING_ADVICE = "trading_advice"
    ACCOUNT_LOOKUP = "account_lookup"
    LOW_CONFIDENCE = "low_confidence"
    KB_GAP = "kb_gap"
    KB_CONFLICT = "kb_conflict"
    TIPPING_OFF = "tipping_off"
    RESERVED_WORDING = "reserved_wording"
    CLIENT_FIGURES = "client_figures"
    GROUNDING_FAILED = "grounding_failed"
    CHECK_ERROR = "check_error"
    DRAFT_ERROR = "draft_error"


# What the agent sees first on the card: why, and what it means for them.
CONSEQUENCE: dict[Reason, str] = {
    Reason.TOO_LONG: "The message is longer than the co-pilot reads: no draft, and not checked for AML, KYC or complaint. Read it and check before replying.",
    Reason.CLASSIFIER_ERROR: "The ticket could not be classified (service unavailable or a bad answer). No draft; read and handle it.",
    Reason.PIPELINE_ERROR: "The co-pilot failed on this ticket. No draft; read and handle it.",
    Reason.PROMPT_INJECTION: "Message tries to instruct the AI. No draft was generated; handle manually.",
    Reason.AML: "Compliance case. Forward to the AML team; the draft only acknowledges.",
    Reason.KYC: "Verification decision. Forward to the KYC team; the draft only acknowledges.",
    Reason.COMPLAINT: "Complaint. A person decides the outcome; the draft only acknowledges.",
    Reason.TRADING_ADVICE: "Asks for trading advice. Never answer that part; a draft, if any, ends with the fixed decline.",
    Reason.ACCOUNT_LOOKUP: "Needs the client's records (transaction, balance, status). Check them before replying.",
    Reason.LOW_CONFIDENCE: "Classifier is unsure about the topic. Read the ticket before using the draft.",
    Reason.KB_GAP: "The help pages do not answer all of it. Fill in what is listed as unanswered.",
    Reason.KB_CONFLICT: "The cited help pages contradict each other. Confirm the current policy first.",
    Reason.TIPPING_OFF: "The draft mentions a compliance, fraud or security check; telling the client could be tipping-off. Withheld.",
    Reason.RESERVED_WORDING: "The draft announces a decision or a handover that only a person can make. Withheld.",
    Reason.CLIENT_FIGURES: "The draft repeats figures from the client's message that the help pages do not state. Check them before sending.",
    Reason.GROUNDING_FAILED: "The draft failed the source check and is withheld.",
    Reason.CHECK_ERROR: "The source check could not run, so the draft is withheld. Reply manually.",
    Reason.DRAFT_ERROR: "Draft generation failed. Reply manually.",
}


@dataclass(frozen=True, slots=True)
class Thresholds:
    """P(yes) above which a flag is raised. Lower where a miss costs more than a false alarm."""

    trading_advice: float = 0.35
    complaint: float = 0.5
    kyc_case: float = 0.5
    aml_case: float = 0.35
    injection: float = 0.5
    account_lookup: float = 0.5
    category_min: float = 0.5  # below this the topic itself is uncertain
    reply_flag: float = 0.5  # a reply question at or above this withholds the draft


@dataclass(frozen=True, slots=True)
class Signals:
    too_long: bool = False
    classifier_error: bool = False
    pipeline_error: bool = False
    injection: bool = False
    aml: bool = False
    kyc: bool = False
    complaint: bool = False
    trading_advice: bool = False
    account_lookup: bool = False
    low_confidence: bool = False
    abstained: bool = False
    unanswered: bool = False
    cites_conflict: bool = False
    tipping_off: bool = False
    reserved_wording: bool = False
    client_figures: bool = False
    grounding_failed: bool = False
    check_error: bool = False
    draft_error: bool = False


@dataclass(frozen=True, slots=True)
class Route:
    reasons: tuple[Reason, ...] = field(default_factory=tuple)

    @property
    def to_human(self) -> bool:
        return bool(self.reasons)

    @property
    def label(self) -> str:
        return "human" if self.reasons else "auto"


_TABLE: tuple[tuple[str, Reason], ...] = (
    ("too_long", Reason.TOO_LONG),
    ("classifier_error", Reason.CLASSIFIER_ERROR),
    ("pipeline_error", Reason.PIPELINE_ERROR),
    ("injection", Reason.PROMPT_INJECTION),
    ("aml", Reason.AML),
    ("kyc", Reason.KYC),
    ("complaint", Reason.COMPLAINT),
    ("trading_advice", Reason.TRADING_ADVICE),
    ("account_lookup", Reason.ACCOUNT_LOOKUP),
    ("low_confidence", Reason.LOW_CONFIDENCE),
    ("abstained", Reason.KB_GAP),
    ("unanswered", Reason.KB_GAP),
    ("cites_conflict", Reason.KB_CONFLICT),
    ("tipping_off", Reason.TIPPING_OFF),
    ("reserved_wording", Reason.RESERVED_WORDING),
    ("client_figures", Reason.CLIENT_FIGURES),
    ("grounding_failed", Reason.GROUNDING_FAILED),
    ("check_error", Reason.CHECK_ERROR),
    ("draft_error", Reason.DRAFT_ERROR),
)


def route(signals: Signals) -> Route:
    """Reasons in table order (most severe first), without duplicates."""
    reasons: list[Reason] = []
    for attr, reason in _TABLE:
        if getattr(signals, attr) and reason not in reasons:
            reasons.append(reason)
    return Route(tuple(reasons))

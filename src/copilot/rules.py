"""Deterministic patterns. Inputs: high-precision signals that run before any model.
Outputs: checks on the draft that do not depend on the model behaving."""

import re
from typing import Final

# --- input side -------------------------------------------------------------

_INJECTION: Final = re.compile(
    r"(?i)("
    r"ignore (all |any |the )?(previous|prior|above|earlier) (instructions|rules|prompts?)"
    r"|disregard (your|the|all) (rules|instructions|guidelines)"
    r"|(reveal|print|show|repeat) (me )?(your|the) (system )?(prompt|instructions)"
    r"|system prompt|developer mode|you are now|act as (an?|my) (?!support)"
    r"|игнорируй (все )?(предыдущие|прошлые)? ?(инструкции|правила)"
    r"|забудь (все )?(инструкции|правила)|системн\w+ промпт|ты теперь"
    r")"
)

_TRADING_ADVICE_REQUEST: Final = re.compile(
    r"(?i)("
    r"\bshould i (buy|sell|go long|go short|open a (long|short)|trade|invest)"
    r"|\b(buy|sell) (now )?or (wait|hold|sell|buy)"
    r"|\bwhat (should|do you think) i (trade|buy|sell)"
    r"|\b(trading )?signals?\b|\bprice (target|prediction|forecast)"
    r"|\bwhich (pair|instrument|stock|coin|asset)s? (will|to)"
    r"|\bwhat leverage should\b|\bwhich leverage (is best|should)|\bbest leverage\b"
    r"|\bwill (gold|xau|eur\/?usd|bitcoin|btc|oil|the dollar|the price) (go|rise|fall|drop|move)"
    r"|стоит ли (покупать|продавать|купить|продать|входить)"
    r"|(купить|покупать) или (продать|продавать|ждать|подождать)"
    r"|какое плечо (лучше|выбрать|поставить)|сигнал\w*|прогноз\w* (по|на|цен)"
    r")"
)


def looks_like_injection(text: str) -> bool:
    return _INJECTION.search(text) is not None


def asks_trading_advice(text: str) -> bool:
    return _TRADING_ADVICE_REQUEST.search(text) is not None


# --- output side --------------------------------------------------------------

_ADVICE_IN_DRAFT: Final = re.compile(
    r"(?i)("
    r"\b(i|we) (would )?(recommend|suggest|advise) (you )?(to )?(buy|sell|go long|go short|trade|use a leverage|use leverage|choose a leverage)"
    r"|\byou should (buy|sell|go long|go short|open a (long|short))"
    r"|\b(good|great|right) time to (buy|sell|invest)"
    r"|\bwill (likely |probably )?(rise|fall|go up|go down)\b"
    r"|\bprice target\b"
    r"|рекомендуем (вам )?(купить|продать|покупать|продавать)"
    r"|(сейчас )?(хорошее|удачное) время (для покупки|для продажи|покупать|продавать)"
    r"|(вероятно|скорее всего) (вырастет|упадет|упадёт)"
    r")"
)

# A reply to a complaint, KYC or AML ticket acknowledges; these phrases announce an outcome.
_DECISION_LANGUAGE: Final = re.compile(
    r"(?i)("
    r"\b(has|have) been (approved|rejected|declined|accepted|unblocked|unfrozen)"
    r"|\bwe (will|'ll) (refund|compensate|reimburse|unblock|unfreeze|approve|reject)"
    r"|\byou (are|will be) (refunded|compensated|reimbursed)"
    r"|\b(is|are) (approved|verified) now\b"
    r"|(одобрен|отклонен|отклонён)\w*"
    r"|(вернём|вернем|компенсируем|разблокируем)"
    r")"
)

# The knowledge base says nothing about fees, so any statement about them is invented.
_POLICY_CLAIM: Final = re.compile(
    r"(?i)("
    r"\bno (fees?|commissions?|charges?)\b|\bfree of charge\b|\b(fee|commission)[- ]free\b"
    r"|\bwithout (any )?(fees?|commissions?)\b|\bwe (do not|don't) charge\b"
    r"|\bguarantee[ds]?\b"
    r"|без комисси\w*|бесплатн\w*|гарантир\w*"
    r")"
)

_NUMBER: Final = re.compile(r"\d+(?::\d+)?(?:[.,]\d+)?")
_LIST_MARKER: Final = re.compile(r"(?m)^\s*\d+[.)]\s")

# Canonical time units, so an English source supports a Russian or Spanish reply.
_TIME_UNITS: Final = {
    "minute": re.compile(r"(?i)\b(minutes?|mins?|минут\w*|minutos?|menit)\b"),
    "hour": re.compile(r"(?i)\b(hours?|hrs?|час\w*|horas?|jam)\b"),
    "day": re.compile(r"(?i)\b(days?|business days?|дн(я|ей|и)|день|сутк\w*|суток|días?|hari)\b"),
    "week": re.compile(r"(?i)\b(weeks?|недел\w*|semanas?|minggu)\b"),
    "month": re.compile(r"(?i)\b(months?|месяц\w*|mes(es)?|bulan)\b"),
}


def numbers(text: str) -> set[str]:
    """Numbers as written, normalised so that "8", "8.00" and "8,0" compare equal.
    Numbered-list markers are formatting, not claims, and are skipped."""
    out = set()
    for raw in _NUMBER.findall(_LIST_MARKER.sub(" ", text)):
        n = raw.replace(",", ".")
        if "." in n:
            n = n.rstrip("0").rstrip(".")
        out.add(n)
    return out


def time_units(text: str) -> set[str]:
    return {unit for unit, pattern in _TIME_UNITS.items() if pattern.search(text)}


def gives_trading_advice(text: str) -> bool:
    return _ADVICE_IN_DRAFT.search(text) is not None


def announces_decision(text: str) -> bool:
    return _DECISION_LANGUAGE.search(text) is not None


def policy_claims(text: str) -> list[str]:
    return [m.group() for m in _POLICY_CLAIM.finditer(text)]

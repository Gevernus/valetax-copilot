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

# Only a person decides a complaint, KYC or AML outcome; these phrases announce one. High
# precision first: a passive outcome counts when the sentence opens with the client's own thing
# ("Your withdrawal was approved") or says "now / already / successfully"; "once it is approved"
# does not. The reply questions (classify/questions.py: REPLY) catch the paraphrases.
_OUTCOME: Final = (
    r"(approved|verified|rejected|declined|denied|accepted|unblocked|unfrozen|blocked|frozen"
    r"|refunded|released|reinstated|suspended|cancell?ed|closed|restricted|complete|completed)"
)
_SENTENCE_START: Final = r"(?:^|(?<=[.!?\n]))\s*"
_DECISION_LANGUAGE: Final = re.compile(
    r"(?i)("
    rf"{_SENTENCE_START}your(\s+[\w'-]+){{1,5}}?\s+(is|are|was|were|has|have|had)"
    rf"(\s+(now|already|successfully|fully|finally|just|not))*(\s+been)?\s+{_OUTCOME}\b"
    r"|\b(is|are|was|were|has been|have been)(\s+(now|already|successfully|fully|finally))+"
    rf"\s+{_OUTCOME}\b"
    rf"|\b(we|i)('ve| have)?(\s+(now|already|successfully|just))*\s+{_OUTCOME}\b"
    r"|\bwe (will|'ll) (refund|compensate|reimburse|unblock|unfreeze|approve|reject|release)\b"
    r"|\byou (have been|are now) (refunded|compensated|reimbursed|verified)\b"
    rf"|{_SENTENCE_START}ваш\w*(\s+[\w-]+){{0,5}}?\s+"
    r"(одобрен|отклонен|отклонён|верифицирован|разблокирован|заблокирован|заморожен|приостановлен"
    r"|отменён|отменен|возвращен|возвращён|подтвержд[её]н)[аоы]?\b"
    r"|\bмы (уже )?(одобрили|отклонили|разблокировали|заблокировали|верифицировали|вернули"
    r"|компенсировали|возместили|заморозили|разморозили|подтвердили)\b"
    r"|\b(вернём|вернем|компенсируем|разблокируем|возместим)\b"
    rf"|{_SENTENCE_START}(su|tu)(\s+[\w-]+){{1,5}}?\s+(fue|fueron|ha sido|han sido|está|están)"
    r"(\s+(ya|ahora|correctamente))*\s+(aprobad|rechazad|verificad|denegad|desbloquead|bloquead"
    r"|reembolsad|cancelad)[ao]s?\b"
    r"|\bhemos (aprobado|rechazado|verificado|desbloqueado|bloqueado|reembolsado|cancelado)\b"
    r"|\b(reembolsaremos|devolveremos|aprobaremos)\b"
    r")"
)

# Telling a client they are under an AML, fraud or compliance check can itself be an offence
# (tipping-off); no reply names one.
_TIPPING_OFF: Final = re.compile(
    r"(?i)("
    r"\bAML\b|\b(anti-)?money laundering\b|\bcompliance\b|\banti-fraud\b|\bflagged\b"
    r"|\bfraud (check|team|review|department|system|monitoring|investigation)s?\b"
    r"|\binvestigat(e|es|ed|ing|ion|ions)\b|\bsuspicious\b"
    r"|\b(security|risk) (team|review|check|department|service)s?\b"
    r"|\bsource of (your |the )?(funds|wealth|income)\b"
    r"|\bотмывани\w*|\bкомплаенс\w*|\bфинмониторинг\w*|\bрасследовани\w*|\bподозрительн\w*"
    r"|\bмошенни\w*|\bслужб\w* безопасности\b|\bисточник\w* (ваших )?(средств|дохода|доходов)\b"
    r"|\blavado de (dinero|activos)\b|\bcumplimiento\b|\binvestigaci[oó]n\b|\bsospechos[ao]s?\b"
    r"|\bfraude\b|\borigen de (los |sus )?fondos\b|\bequipo de seguridad\b"
    r")"
)

# A draft is a proposal to the agent; nothing has been handed over when the client reads it.
_HANDOVER: Final = re.compile(
    r"(?i)("
    r"\b(is|was|were|has been|have been) (passed|forwarded|escalated|transferred|referred)"
    r" (on )?to\b"
    r"|\b(i|we)('ve| have)? (passed|forwarded|escalated|transferred|referred)\b"
    r"|\b(мы|я) (уже )?передал\w*\b"
    r"|\bпереда(н|на|но|ны)\s+(в|во|ответствен\w*|команд\w*|отдел\w*|специалист\w*|сотрудник\w*"
    r"|коллег\w*)\b|\bпереда(н|на|но|ны)[.!]"
    r"|\b(fue|fueron|ha sido|han sido) (remitid|transferid|derivad|escalad|trasladad)[ao]s?\b"
    r"|\bhemos (remitido|transferido|derivado|pasado|escalado|trasladado)\b"
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


def gives_trading_advice(text: str) -> bool:
    return _ADVICE_IN_DRAFT.search(text) is not None


def announces_decision(text: str) -> bool:
    return _DECISION_LANGUAGE.search(text) is not None


def tips_off(text: str) -> bool:
    return _TIPPING_OFF.search(text) is not None


def claims_handover(text: str) -> bool:
    return _HANDOVER.search(text) is not None


def policy_claims(text: str) -> list[str]:
    return [m.group() for m in _POLICY_CLAIM.finditer(text)]

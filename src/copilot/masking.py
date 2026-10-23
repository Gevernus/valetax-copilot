"""PII masking. Runs first; nothing downstream (models, logs, traces) sees the raw ticket.

Masked, exactly: emails; card numbers of 13-19 digits that pass the Luhn check, with at most
one separator character (space, tab, hyphen, dot or line break) between two digits; IBANs in
any case, with at most one space or hyphen between groups; TRON, EVM and bc1 wallet addresses;
phones with a "+" right before the first digit; 5+ digits right after an account, login, MT4/5
or ID keyword; any run of 7+ digits; an identity document token right after its keyword
("passport A12345678", "DNI 12345678Z", "паспорт серия 4510"). Anything else is not masked,
"4111 - 1111 - ..." (three characters between groups), "+ 7 916 ..." and "my account is
12345" included.

Not masked: names, addresses and dates of birth; local phone formats ("8 (916) 123-45-67");
other wallet formats (legacy Bitcoin, DOGE, SOL); national numbers without a keyword or in
dotted form (CPF, Aadhaar, PAN, SSN, "DNI 12.345.678-Z"); a passport number written apart from
its series ("серия 4510 номер 123456" masks the series only). All of these reach the classifier
and drafter vendors (docs/decisions.md §16); names and addresses need a named-entity model, the
rest a longer list, which the vendor review decides on.
"""

import re
from collections import Counter
from dataclasses import dataclass

from copilot.normalise import normalise

# Anchored at the start of a run, so a long run without "@" is scanned once, not from every
# position in it.
_EMAIL = re.compile(r"(?<![\w.+-])[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
# Any case, grouped by spaces or hyphens; at least 10 digits, so "en12 this text" is not one.
_IBAN = re.compile(r"(?i)\b[A-Z]{2}\d{2}(?:[\s-]?[A-Z0-9]{4}){2,7}(?:[\s-]?[A-Z0-9]{1,4})?\b")
_IBAN_MIN_DIGITS = 10
# Groups split by a space, tab, hyphen, dot or line break (normalise keeps wide gaps as a tab).
_CARD = re.compile(r"(?<!\d)\d(?:[ \t\n.-]?\d){12,18}(?!\d)")
_WALLET = re.compile(r"\b(?:T[1-9A-HJ-NP-Za-km-z]{33}|0x[0-9a-fA-F]{40}|(?i:bc1[0-9a-z]{25,59}))\b")
_PHONE = re.compile(r"(?<![\d+])\+\d[\d\s().-]{7,}\d")
# Account and login numbers: a keyword followed by 5+ digits, or any bare run of 7+ digits.
_ACCOUNT_KEYWORD = re.compile(
    r"(?i)\b(account|acc|login|mt[45]|id|счет|счёт|счета|логин|аккаунт)"
    r"(\s{0,3}(?:no\.?|number|№|#)?[ \t]{0,2}:?\s{0,3})"
    r"(\d{5,})"
)
_LONG_NUMBER = re.compile(r"(?<!\d)\d{7,}(?!\d)")  # glued to letters too: "ID1234567"
# Identity documents: a keyword, then a token with a digit in it ("A12345678", "12345678Z",
# "4510 123456"). A bare "ID" is left to the account rule: it is usually a login.
_ID_DOCUMENT = re.compile(
    r"(?i)\b(passports?|pasaporte|DNI|NIE|national id|id card|id number|identity (?:card|number)"
    r"|паспорт\w*)"
    r"(\s{0,3}(?:no\.?|number|num\.?|nº|№|#|номер|серия)?[ \t]{0,2}:?\s{0,3})"
    r"([a-z]{0,3}\d[a-z\d]{3,15}(?:[ -]\d{3,10})?)\b"
)


@dataclass(frozen=True, slots=True)
class Masked:
    """Masked text and how many items of each kind were masked."""

    text: str
    counts: dict[str, int]  # what was masked, by kind; safe to log


def _luhn_ok(digits: str) -> bool:
    total = 0
    for i, ch in enumerate(reversed(digits)):
        d = int(ch)
        if i % 2 == 1:
            d = d * 2 - 9 if d > 4 else d * 2
        total += d
    return total % 10 == 0


def mask_pii(text: str) -> Masked:
    """Mask emails, cards, IBANs, wallets, phones, account and ID numbers in the normalised text.

    `normalise` is idempotent, so a caller that already normalised loses nothing, and an invisible
    character cannot split an email or a number.
    """
    text = normalise(text)
    counts: Counter[str] = Counter()

    def sub(pattern: re.Pattern[str], label: str, s: str) -> str:
        def repl(m: re.Match[str]) -> str:
            counts[label] += 1
            return f"[{label}]"

        return pattern.sub(repl, s)

    def iban(m: re.Match[str]) -> str:
        if sum(ch.isdigit() for ch in m.group()) >= _IBAN_MIN_DIGITS:
            counts["IBAN"] += 1
            return "[IBAN]"
        return m.group()

    def card(m: re.Match[str]) -> str:
        digits = re.sub(r"\D", "", m.group())
        if _luhn_ok(digits):
            counts["CARD"] += 1
            return "[CARD]"
        return m.group()

    def account(m: re.Match[str]) -> str:
        counts["ACCOUNT"] += 1
        return f"{m.group(1)}{m.group(2)}[ACCOUNT]"

    def id_document(m: re.Match[str]) -> str:
        counts["ID"] += 1
        return f"{m.group(1)}{m.group(2)}[ID]"

    out = sub(_EMAIL, "EMAIL", text)
    out = sub(_WALLET, "WALLET", out)  # before cards: an address can hold a Luhn-valid run
    out = _IBAN.sub(iban, out)
    out = _CARD.sub(card, out)
    out = sub(_PHONE, "PHONE", out)
    out = _ID_DOCUMENT.sub(id_document, out)
    out = _ACCOUNT_KEYWORD.sub(account, out)
    out = sub(_LONG_NUMBER, "NUMBER", out)
    return Masked(out, dict(counts))

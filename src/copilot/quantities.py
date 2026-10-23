"""Numbers with their units, normalised so that a draft and its sources compare by value.

`quantities(text)` returns every number with the unit or currency bound to it; `supported`
says whether a claim has the same value and unit in the evidence. "8", "8.00" and "8,0" are one
value; "3 days" is not "3 hours", "$10" is not "10 USDT" or "10%", and a bare "8" is not "8 USD".
A separator that reads differently by locale ("1,000") keeps both readings, and only the same
readings support it.

Read, in English, Russian and Spanish (the languages with ready drafts): digits with any
thousands separator and multipliers ("10k", "50 тысяч"); currencies as symbols or codes on
either side and as words after the number; time units, percent, lots and pips; ranges ("1-2
days") bind the unit to both ends. A step's number ("Step 4") and a count of steps ("3 simple
steps") have their own units, so the help page's steps never stand behind an amount. A number
written as a word before a unit ("two business days") keeps the word as its value: the sources
write digits, so only the client's own words can stand behind it.

Fails closed: a number followed by any word the tables do not know ("3 pounds", "2 trading
days", "60 menit") has the unit "unknown" and nothing supports it.

`time_units` finds time words without a digit ("within the hour"), apart from greetings and
idioms.
"""

import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Final, NamedTuple


@dataclass(frozen=True, slots=True)
class Quantity:
    """A number and its unit, the way a claim is compared."""

    values: frozenset[str]  # canonical decimals; two when the separator is ambiguous
    unit: str | None  # canonical unit, None for a bare number

    def __str__(self) -> str:
        value = " or ".join(sorted(self.values, key=lambda v: (len(v), v)))
        if self.unit is None:
            return value
        if self.unit == "percent":
            return f"{value}%"
        if self.unit == "step":
            return f"step {value}"
        if self.unit == "unknown":
            return f"{value} (unit not recognised)"
        label = unit_label(self.unit)
        if self.values == {"1"} and label.endswith("s") and label.islower():
            label = label[:-1]
        return f"{value} {label}"


# Latin and Cyrillic letters: a unit word must not run into one ("hours" in "hourslong").
_LETTER: Final = r"A-Za-zÀ-ɏЀ-ӿ"
_START, _END = rf"(?<![{_LETTER}\d])", rf"(?![{_LETTER}])"

# Canonical time unit -> (words that are a time claim anywhere, "within the hour"; words that
# count only right after a number: "48h" is a duration, "Min. deposit" is not).
_TIME: Final = {
    "minute": (r"minutes?|минут[аыу]?|minutos?", r"mins?"),
    "hour": (r"hours?|час(?:а|ов|ам|ами)?|пол(?:у)?часа|horas?", r"hrs?|h"),
    "business_day": (
        r"(?:business|working|banking) days?|рабоч\w+ (?:дн(?:я|ей|и|ям)|день|сут\w+)"
        r"|d[ií]as? (?:h[aá]biles|laborables)",
        "",
    ),
    "day": (r"(?:calendar )?days?|дн(?:я|ей|и|ям|ями|ях)|день|сутк\w*|суток|d[ií]as?", ""),
    "week": (r"weeks?|недел\w*|semanas?", ""),
    "month": (r"months?|месяц\w*|mes(?:es)?", ""),
    "year": (r"years?|год(?:а|у|ом)?|лет|años?", ""),
}
# Canonical currency -> (symbols and codes, before or after the number; words, after it).
_CURRENCY: Final = {
    "usdt": (r"usdt", r"tether"),
    "usd": (r"us\$|\$|usd", r"us dollars?|dollars?|доллар\w*|d[oó]lar(?:es)?"),
    "eur": (r"€|eur", r"euros?|евро"),
    "rub": (r"₽|rub|руб\.?", r"рубл\w*|roubles?|rubles?|rublos?"),
    "gbp": (r"£|gbp", r"pounds? sterling"),
}
_OTHER: Final = {
    "percent": r"%|percent|per cent|процент\w*|por ciento",
    "lot": r"lots?|лот(?:а|ов|ы)?|lotes?",
    "pip": r"pips?",
}
_LABELS: Final = {"minute": "minutes", "hour": "hours", "business_day": "business days",
                  "day": "days", "week": "weeks", "month": "months", "year": "years",
                  "lot": "lots", "pip": "pips", "steps": "steps"}  # fmt: skip

_UNIT_WORDS: Final = {
    **{name: "|".join(p for p in pair if p) for name, pair in _TIME.items()},
    **{name: f"{codes}|{words}" for name, (codes, words) in _CURRENCY.items()},
    **_OTHER,
}
# Right after a number: "48 hours", "48h", "24-hour", "10 %", "10 $".
_UNIT_AFTER: Final = re.compile(
    r"(?i)[  -]?(?:" + "|".join(f"(?P<{n}>{w})" for n, w in _UNIT_WORDS.items()) + rf"){_END}"
)
# A unit the tables do not know, which no source can then support: a currency sign or an
# upper-case code ("₹2", "2 AUD", "2 BTC"); any other unknown word after the number is caught by
# `_unknown_unit` below.
_SIGN: Final = r"[¢-¥฿₠-⃏]"
_UNKNOWN_AFTER: Final = re.compile(rf"[  ]?{_SIGN}|[  ]?[A-Z]{{3,4}}(?![A-Za-z])")
_UNKNOWN_BEFORE: Final = re.compile(rf"(?:{_SIGN}|(?<![A-Za-z])[A-Z]{{3,4}})[  ]?$")
_TIME_ANYWHERE: Final = {
    name: re.compile(rf"(?i){_START}(?:{words}){_END}") for name, (words, _) in _TIME.items()
}
# Greetings and idioms with a time word that state no timeline: "good day", "24 hours a day".
_IDIOM: Final = re.compile(
    r"(?i)\b(?:good|nice|great|lovely|wonderful) day\b|\bbuen(?:os)? d[ií]as?\b"
    r"|\bдобр(?:ый|ого) (?:день|дня)\b|\bхорошего дня\b|\b(?:a|en) cualquier hora\b|\bany time\b"
    r"|\b(?:wait|just) a (?:minute|moment)\b"
    r"|(?<=\d)(?:\s+[\w-]+)?\s+(?:a|per|each) (?:day|week|month|hour|year)\b"
)
# A whitelist: the only words that may follow a number without making it a claim about
# something else (function words and ordinal endings). Any other word right after a number
# ("3 pounds", "2 cycles") is a unit the tables do not know.
_BARE_NEXT: Final = frozenset(
    "and or to of in on at for from with by per up is are was were will can may the a an "
    "depending st nd rd th и или в на до от по для с из й я е го ый ая ое ой y o de en para "
    "por con".split()
)
# Steps: a step's number ("Step 2", "Шаг 2", "the 2nd step") and a count of steps ("3 simple
# steps") have their own units, so the help page's "Step 4" never stands behind "the minimum
# deposit is 4".
_STEP_PLURALS: Final = r"steps|шаги|шагов|pasos"
_STEP_WORDS: Final = rf"{_STEP_PLURALS}|step|шага?|paso"
_STEP_ADJECTIVES: Final = (
    r"simple|easy|quick|short|few|following|прост\w+|лёгк\w+|легк\w+|быстр\w+|sencill\w+"
    r"|fácil\w*|rápid\w+"
)
_STEP_BEFORE: Final = re.compile(rf"(?i)(?:{_STEP_WORDS})[^\S\n]*(?:#|№)?[^\S\n]*$")
# The end of a range after a plural step word ("steps 1-4"). A currency sign or code after it
# still wins ("steps 1-4 AUD").
_STEP_RANGE_BEFORE: Final = re.compile(
    rf"(?i)(?:{_STEP_PLURALS})[^\S\n]*\d+[^\S\n]*(?:-|–|—|to|до|a)[^\S\n]*$"
)
# After the number: an ordinal ending, at most one adjective (or two joined by "and") from the
# closed list, then the step word. Nothing else may stand between, so "3 AUD per step" is not
# a step.
_STEP_AFTER: Final = re.compile(
    rf"(?i)(?P<ord>st|nd|rd|th|-?й)?(?:[^\S\n]+(?:{_STEP_ADJECTIVES})"
    rf"(?:[^\S\n]+(?:and|и|y)[^\S\n]+(?:{_STEP_ADJECTIVES}))?)?"
    rf"[^\S\n]*(?:{_STEP_WORDS})(?![^\W\d_])"
)
# Digits inside names, not amounts.
_NOT_A_CLAIM: Final = re.compile(r"(?i)\b(?:24/7|2fa|3ds)\b")
_NEXT_WORD: Final = re.compile(r"[^\S\n]*-?([^\W\d_]+)")

_PREFIX_CODES: Final = {name: codes for name, (codes, _) in _CURRENCY.items()}
_SYMBOL: Final = re.compile(r"[^\W\d]")  # a prefix with no letter in it is a symbol: "$", "€"
_MULTIPLIERS: Final = {
    "thousand": (r"k|thousands?|тыс\.?|тысяч\w*|mil", 10**3),
    "million": (r"millions?|mln|millones|millón|млн\.?|миллион\w*", 10**6),
    "billion": (r"billions?|bn|миллиард\w*|млрд\.?", 10**9),
}
_NUMBER: Final = re.compile(
    rf"(?i)(?:{_START}(?P<pre>"
    + "|".join(f"(?P<pre_{n}>{c})" for n, c in _PREFIX_CODES.items())
    + rf")[  ]?|(?<![{_LETTER}\d_.,:]))"
    r"(?P<num>\d{1,3}(?:[   ]\d{3})+(?!\d)|\d+:\d+|\d+(?:[.,]\d+)*)"
    r"(?:[  ]?(?:"
    + "|".join(f"(?P<x_{n}>{p})" for n, (p, _) in _MULTIPLIERS.items())
    + rf"){_END})?"
)
# Number words, counted only right before a unit. The drafter is told to write digits, so a
# word is kept as written and compared as text ("two business days").
_NUMBER_WORD: Final = (
    r"one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|fifteen|twenty|thirty"
    r"|forty|fifty|sixty|hundred|thousand"
    r"|од(?:ин|н\w+)|дв[аеу]\w*|тр[иеё]\w*|четыр\w+|пят\w+|шест\w+|сем\w+|восем\w+|девят\w+"
    r"|десят\w+|двадцат\w+|тридцат\w+|сорок\w*|сто|тысяч\w*"
    r"|uno?|una|dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez|once|doce|quince|veinte"
    r"|veinti\w+|treinta|cuarenta|cien|ciento|mil"
)
_WORD_RUN: Final = re.compile(
    rf"(?i)(?<![\w-])(?:{_NUMBER_WORD})(?:(?:[ -]|\s+(?:and|y)\s+)(?:{_NUMBER_WORD}))*(?![\w-])"
)
# "1. Log in. 2. Select" or "1) Visit": list numbering at a line start or after a sentence,
# stripped only as a sequence 1, 2, ... of at least two ("1) …; 2) …" too). A marker after ":"
# may only start one, so "Minimum deposit: 4." after a list, "Fee: 1." or "(3)" stays a figure.
_LIST_MARKER: Final = re.compile(r"(?m)(?:^|(?<=[.!?:;]))[ \t]*(?P<n>\d{1,2})[.)](?=\s)")
# Between two numbers, these make a range or a list, so a unit after the second one applies to
# the first too: "1-2 days", "два и три дня".
_RANGE: Final = re.compile(r"(?i)\s*(?:-|–|—|to|or|and|y|o|a|и|или|до)\s*")


def _canonical(d: Decimal) -> str:
    return format(d.normalize(), "f")


def _readings(raw: str) -> set[Decimal] | None:
    """Every value the digits can mean, or None if they are not one number ("1,2,3")."""
    raw = re.sub(r"[   ]", "", raw)
    seps = re.findall(r"[.,]", raw)
    groups = re.split(r"[.,]", raw)
    if not seps:
        return {Decimal(raw)}
    head, tail = groups[0], groups[1:]
    grouped = len(head) <= 3 and head[0] != "0"
    if len(seps) == 1:
        decimal = {Decimal(f"{head}.{tail[0]}")}
        if grouped and len(tail[0]) == 3:
            return decimal | {Decimal(head + tail[0])}  # "1,000": a thousand, or one
        return decimal
    # Several separators: all but the last group thousands, the last one either too.
    if not grouped or any(len(g) != 3 for g in tail[:-1]) or len(set(seps[:-1])) != 1:
        return None
    if seps[-1] == seps[0]:
        return {Decimal("".join(groups))} if len(tail[-1]) == 3 else None
    return {Decimal(f"{''.join(groups[:-1])}.{tail[-1]}")}


def _step_unit(text: str, start: int, end: int) -> str | None:
    """The step unit of a number, if any.

    "step" for a step's number ("Step 2", "the 2nd step"), "steps" for a count of steps ("3
    simple steps"); each supports only its own kind.
    """
    if _STEP_BEFORE.search(text[max(0, start - 24) : start]):
        return "step"
    m = _STEP_AFTER.match(text, end)
    if m is None:
        return None
    return "step" if m.group("ord") else "steps"


def _currency_like(text: str, start: int, end: int) -> bool:
    """A currency sign or an upper-case code the tables do not know, after or before."""
    after = _UNKNOWN_AFTER.match(text, end)
    return bool(after or _UNKNOWN_BEFORE.search(text[max(0, start - 6) : start]))


def _unknown_unit(text: str, start: int, end: int) -> bool:
    if _currency_like(text, start, end):
        return True
    word = _NEXT_WORD.match(text, end)
    return word is not None and word.group(1).lower() not in _BARE_NEXT


def _strip_list_markers(text: str) -> str:
    runs: list[list[re.Match[str]]] = []
    for m in _LIST_MARKER.finditer(text):
        n = int(m.group("n"))
        before = text[m.start() - 1 : m.start()]  # "", "\n" or the punctuation it follows
        if n == 1:
            runs.append([m])
        elif runs and n == int(runs[-1][-1].group("n")) + 1 and before != ":":
            # After ";" only a list already run with ";" or ":" goes on ("1) …; 2) …").
            prev = text[runs[-1][-1].start() - 1 : runs[-1][-1].start()]
            if before != ";" or prev in (";", ":", "\n", ""):
                runs[-1].append(m)
    spans = sorted((m.start(), m.end()) for run in runs if len(run) >= 2 for m in run)
    parts, pos = [], 0
    for start, end in spans:
        parts += [text[pos:start], " "]
        pos = end
    return "".join([*parts, text[pos:]])


def _unit_after(text: str, pos: int) -> str | None:
    m = _UNIT_AFTER.match(text, pos)
    return m.lastgroup if m else None


class _Token(NamedTuple):
    start: int
    end: int
    values: frozenset[str]
    unit: str | None


def _digit_tokens(text: str) -> list[_Token]:
    out: list[_Token] = []
    for m in _NUMBER.finditer(text):
        raw = m.group("num")
        code = next((n for n in _CURRENCY if m.group(f"pre_{n}")), None)
        # "$10" binds tightly; a code yields to a unit after it: "200 USD 2 hours" is hours.
        symbol = code is not None and not _SYMBOL.search(m.group("pre"))
        unit = code if symbol else _unit_after(text, m.end()) or code
        start = m.start("num")
        if unit is None:
            unit = _step_unit(text, start, m.end())
        # A ratio ("1:2000") carries no unit: the word after it is not one. A step range ("steps
        # 1-4") yields to a currency sign or code, not to any other word ("steps 1-4 below").
        if unit is None and ":" not in raw and _currency_like(text, start, m.end()):
            unit = "unknown"
        if unit is None and _STEP_RANGE_BEFORE.search(text[max(0, start - 24) : start]):
            unit = "step"
        if unit is None and ":" not in raw and _unknown_unit(text, start, m.end()):
            unit = "unknown"
        if ":" in raw:
            out.append(_Token(start, m.end(), frozenset({raw}), unit))
            continue
        readings = _readings(raw)
        if readings is None:  # a list or a version string: each part on its own
            out += [
                _Token(start, m.end(), frozenset({str(int(g))}), None)
                for g in re.split(r"[.,]", raw)
            ]
            continue
        factor = next((f for n, (_, f) in _MULTIPLIERS.items() if m.group(f"x_{n}")), 1)
        values = frozenset(_canonical(r * factor) for r in readings)
        out.append(_Token(start, m.end(), values, unit))
    return out


def _word_tokens(text: str, digits: list[_Token]) -> list[_Token]:
    """Number words right before a unit, the words themselves as the value.

    A word inside a digit token ("10 mil USD") is its multiplier, not a number of its own.
    """
    out = []
    for m in _WORD_RUN.finditer(text):
        unit = _unit_after(text, m.end())
        if unit is not None and not any(t.start <= m.start() < t.end for t in digits):
            words = " ".join(re.findall(r"[^\W\d_]+", m.group().lower()))
            out.append(_Token(m.start(), m.end(), frozenset({words}), unit))
    return out


def quantities(text: str) -> set[Quantity]:
    """Every number in the text with the unit or currency attached to it.

    Numbered-list markers are formatting, and number words count only before a unit ("one of
    our agents" is not a claim).
    """
    text = _NOT_A_CLAIM.sub(" ", _strip_list_markers(text))
    digits = _digit_tokens(text)
    tokens = sorted([*digits, *_word_tokens(text, digits)])
    for i in range(len(tokens) - 2, -1, -1):
        a, b = tokens[i], tokens[i + 1]
        if a.unit is None and b.unit and _RANGE.fullmatch(text, a.end, b.start):
            tokens[i] = a._replace(unit=b.unit)
    return {Quantity(t.values, t.unit) for t in tokens}


def supported(claim: Quantity, evidence: set[Quantity]) -> bool:
    """Whether the evidence holds the same value with the same unit.

    A bare number is supported only by a bare number, and a number with an unknown unit by
    nothing.
    """
    return claim.unit != "unknown" and claim in evidence


def unit_label(unit: str) -> str:
    """The unit as a card shows it: "hours", "USD"."""
    return _LABELS.get(unit, unit.upper())


def time_units(text: str) -> set[str]:
    """Time units mentioned without a number ("within the hour"), apart from greetings and idioms."""
    text = _IDIOM.sub(" ", text)
    return {unit for unit, pattern in _TIME_ANYWHERE.items() if pattern.search(text)}

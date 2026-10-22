"""Numbers with their units, normalised so that a draft and its sources compare by value.

"8", "8.00" and "8,0" are one value; "$1,000" is never "1"; "two business days" is the same
claim as "2 business days"; "3 days" is not "3 hours", "$10" is not "10 USDT", "10 EUR" or "10%",
and a bare "8" is not "8 USD". A separator that reads differently by locale ("1,000" is a
thousand in English, one in Russian) keeps both readings, and only a number with the same
readings supports it.

Covered: digits with any thousands separator; multipliers ("10k", "50 тысяч", "2 млн");
currencies as symbols or codes before or after the number, glued or spaced ("$10", "10 $",
"USD500", "8 €"), and as words after it; time units, the main currency words and percent in
every language `language.py` detects; spelled-out numbers below a million in English, Russian
(hundreds only as "сто"), Spanish and Indonesian, counted only before a unit; ranges ("1-2
business days", "два и три дня") bind the unit to both ends. A unit the tables do not know
leaves the number bare, and only a bare number supports a bare number.
"""

import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Final, NamedTuple


@dataclass(frozen=True, slots=True)
class Quantity:
    values: frozenset[str]  # canonical decimals; two when the separator is ambiguous
    unit: str | None  # canonical unit, None for a bare number

    def __str__(self) -> str:
        value = " or ".join(sorted(self.values, key=lambda v: (len(v), v)))
        if self.unit is None:
            return value
        if self.unit == "percent":
            return f"{value}%"
        label = _LABELS.get(self.unit, self.unit.upper())
        if self.values == {"1"} and label.endswith("s") and label.islower():
            label = label[:-1]
        return f"{value} {label}"


# Letters of the scripts that separate words with spaces. A unit word must not run into one of
# them ("hours" in "hourslong"); Chinese and Thai are written without spaces ("60分钟内").
_LETTER: Final = (
    r"A-Za-z\u00c0-\u024f\u1e00-\u1eff\u0400-\u04ff\u0620-\u064a\u066e-\u06d3\u0900-\u0963"
)
_START, _END = rf"(?<![{_LETTER}\d])", rf"(?![{_LETTER}])"

# Canonical time unit -> (words; abbreviations and stems that count only right after a number),
# for every language `language.py` detects. "48h" is a duration, "Min. deposit" is not; Turkish
# adds suffixes to a unit after a number ("6 aylık"), but "ay" elsewhere is not a month.  # noqa: RUF003
_TIME: Final = {
    "minute": (
        r"minutes?|minuten?|минут[аыу]?|хвилин\w*|minutos?|menit|minit|dakika|phút|دقيقة|دقائق"
        r"|دقيقتين|मिनट|นาที|分钟|分鐘",
        r"mins?|dakika\w*",
    ),
    "hour": (
        r"hours?|heures?|stunden?|час(?:а|ов|ам|ами)?|годин\w*|horas?|jam|saat|giờ|tiếng|ساعة"
        r"|ساعات|ساعتين|घंटे|घंटा|घंटों|ชั่วโมง|小时|小時",
        r"hrs?|h|saat\w*",
    ),
    "business_day": (
        r"(?:business|working|banking) days?|рабоч\w+ (?:дн(?:я|ей|и|ям)|день|сут\w+)"
        r"|робоч\w+ дн\w*|d[ií]as? (?:h[aá]biles|laborables|úteis|uteis)|hari (?:kerja|bekerja)"
        r"|jours? ouvr(?:és|ables?)|werktagen?|arbeitstagen?|iş gün\w*|ngày làm việc|أيام عمل"
        r"|يوم عمل|कार्य दिवस|วันทำการ|个工作日|工作日",
        "",
    ),
    "day": (
        r"(?:calendar )?days?|jours?|tagen?|tage|дн(?:я|ей|и|ям|ями|ях|ів)|день|сутк\w*|суток"
        r"|доб\w*|d[ií]as?|hari|gün|ngày|يوم|أيام|ايام|يومين|दिन|दिनों|วัน|天",
        r"gün\w*",
    ),
    "week": (
        r"weeks?|semaines?|wochen?|недел\w*|тижн\w*|тиждень|semanas?|minggu|hafta|tuần|أسبوع"
        r"|أسابيع|सप्ताह|हफ्ते|สัปดาห์|周|星期",
        r"hafta\w*",
    ),
    "month": (
        r"months?|mois|monate?n?|monat|месяц\w*|місяц\w*|місяць|mes(?:es)?|bulan|ay|tháng|شهر"
        r"|أشهر|شهور|महीने|महीना|เดือน|个月",
        r"ay\w*",
    ),
    "year": (
        r"years?|ans|années?|jahre?n?|год(?:а|у|ом)?|лет|рок(?:и|у|ів)?|años?|anos?|tahun|yıl"
        r"|năm|سنة|سنوات|عام|أعوام|साल|वर्ष|ปี|年",
        r"yıl\w*",
    ),
}
# Canonical currency -> (symbols and codes, before or after the number; words, after it).
_CURRENCY: Final = {
    "usdt": (r"usdt", r"tether"),
    "usd": (
        r"us\$|\$|usd",
        r"us dollars?|dollars?|доллар\w*|долар\w*|d[oó]lar(?:es)?|đô la|đô|دولار|دولارات|डॉलर"
        r"|ดอลลาร์|美元|美金",
    ),
    "eur": (r"€|eur", r"euros?|евро|євро|يورو|यूरो|ยูโร|欧元|歐元"),
    "rub": (r"₽|rub|руб\.?", r"рубл\w*|roubles?|rubles?"),
    "idr": (r"rp\.?|idr", r"rupiah"),
    "gbp": (r"£|gbp", r"pounds? sterling"),
}
_OTHER: Final = {
    "percent": (
        r"%|٪|percent|per cent|pour ?cent|prozent|процент\w*|відсот\w*|por ciento|por cento"
        r"|persen|peratus|phần trăm|في المئة|بالمئة|प्रतिशत|เปอร์เซ็นต์"
    ),
    "lot": r"lots?|лот(?:а|ов|ы)?|lotes?",
    "pip": r"pips?",
}
_LABELS: Final = {"minute": "minutes", "hour": "hours", "business_day": "business days",
                  "day": "days", "week": "weeks", "month": "months", "year": "years",
                  "lot": "lots", "pip": "pips"}  # fmt: skip

_UNIT_WORDS: Final = {
    **{name: "|".join(p for p in pair if p) for name, pair in _TIME.items()},
    **{name: f"{codes}|{words}" for name, (codes, words) in _CURRENCY.items()},
    **_OTHER,
}
# Right after a number: "48 hours", "48h", "24-hour", "10 %", "10 $", "60分钟".
_UNIT_AFTER: Final = re.compile(
    r"(?i)[ \u00a0-]?(?:" + "|".join(f"(?P<{n}>{w})" for n, w in _UNIT_WORDS.items()) + rf"){_END}"
)
# A unit the tables do not know, which no source can then support: a currency sign or an
# upper-case code ("₹2", "2 AUD", "2 BTC"), or a known unit with a qualifier in front ("2 trading
# days", "4 working hours", "4 lakh per day").
_SIGN: Final = r"[\u00a2-\u00a5\u0e3f\u20a0-\u20cf]"
_ALL_UNITS: Final = "|".join(_UNIT_WORDS.values())
_UNKNOWN_AFTER: Final = re.compile(
    rf"[ \u00a0]?{_SIGN}|[ \u00a0]?[A-Z]{{3,4}}(?![A-Za-z])"
    rf"|[ \u00a0-](?i:[^\W\d_]+[ -]){{1,2}}(?i:{_ALL_UNITS}){_END}"
)
_UNKNOWN_BEFORE: Final = re.compile(rf"(?:{_SIGN}|(?<![A-Za-z])[A-Z]{{3,4}})[ \u00a0]?$")
_STEP_BEFORE: Final = re.compile(
    r"(?i)(?:step|шаг|paso|passo|langkah|adım|bước|étape|schritt|etapa)\s*$"
)

_PREFIX_CODES: Final = {name: codes for name, (codes, _) in _CURRENCY.items()}
_SYMBOL: Final = re.compile(r"[^\W\d]")  # a prefix with no letter in it is a symbol: "$", "€"
_MULTIPLIERS: Final = {
    "thousand": (r"k|thousands?|тыс\.?|тысяч\w*|mil|ribu", 10**3),
    "million": (r"millions?|mln|millones|millón|млн\.?|миллион\w*|juta", 10**6),
    "billion": (r"billions?|bn|миллиард\w*|млрд\.?|miliar", 10**9),
}
_NUMBER: Final = re.compile(
    rf"(?i)(?:{_START}(?P<pre>"
    + "|".join(f"(?P<pre_{n}>{c})" for n, c in _PREFIX_CODES.items())
    + rf")[ \u00a0]?|(?<![{_LETTER}\d_.,:]))"
    r"(?P<num>\d{1,3}(?:[\u00a0\u202f ]\d{3})+(?!\d)|\d+:\d+|\d+(?:[.,]\d+)*)"
    r"(?:[ \u00a0]?(?:"
    + "|".join(f"(?P<x_{n}>{p})" for n, (p, _) in _MULTIPLIERS.items())
    + rf"){_END})?"
)
# "1. Log in. 2. Select" or "1) Visit": list numbering, not a claim.
_LIST_MARKER: Final = re.compile(
    r"(?m)(?:^|(?<=[.!?:;]))\s*\d{1,2}[.)](?=\s)|(?<![\w.,])\d{1,2}\)(?=\s)"
)
# Between two numbers, these make a range or a list, so a unit after the second one applies to
# the first too: "1-2 days", "two to three days", "два и три дня".
_RANGE: Final = re.compile(r"(?i)\s*(?:-|–|—|to|or|and|y|o|a|и|или|до|hingga|sampai|atau|dan)\s*")


def _number_words() -> dict[str, tuple[int, str]]:
    """Word -> (value, how it combines): "add" to the running number, "mul" multiplies the last
    word ("two hundred", "dua puluh"), "teen" adds ten ("dua belas"), "big" closes a group of
    thousands."""
    add: dict[int, str] = {
        0: "zero cero nol",
        1: "one uno un una satu один одна одно одного одной одному одну одним одном",
        2: "two dos dua два две двух двум двумя двое",
        3: "three tres tiga три трёх трех трём трем тремя трое",
        4: "four cuatro empat четыре четырёх четырех четырём четырем четырьмя четверо",
        5: "five cinco lima пять пяти пятью",
        6: "six seis enam шесть шести шестью",
        7: "seven siete tujuh семь семи семью",
        8: "eight ocho delapan восемь восьми восемью",
        9: "nine nueve sembilan девять девяти девятью",
        10: "ten diez sepuluh десять десяти десятью",
        11: "eleven once sebelas",
        12: "twelve doce",
        13: "thirteen trece",
        14: "fourteen catorce",
        15: "fifteen quince",
        16: "sixteen dieciséis dieciseis",
        17: "seventeen diecisiete",
        18: "eighteen dieciocho",
        19: "nineteen diecinueve",
        20: "twenty veinte",
        21: "veintiuno veintiún veintiuna",
        22: "veintidós veintidos",
        23: "veintitrés veintitres",
        24: "veinticuatro",
        25: "veinticinco",
        26: "veintiséis veintiseis",
        27: "veintisiete",
        28: "veintiocho",
        29: "veintinueve",
        30: "thirty treinta",
        40: "forty cuarenta сорок сорока",
        50: "fifty cincuenta пятьдесят пятидесяти",
        60: "sixty sesenta шестьдесят шестидесяти",
        70: "seventy setenta семьдесят семидесяти",
        80: "eighty ochenta восемьдесят восьмидесяти",
        90: "ninety noventa девяносто девяноста",
        100: "cien ciento seratus сто ста",
        1000: "seribu",
    }
    # Russian 11-19, 20 and 30 decline alike: двадцать, двадцати, двадцатью.
    for value, word in [(11, "одиннадцать"), (12, "двенадцать"), (13, "тринадцать"),
                        (14, "четырнадцать"), (15, "пятнадцать"), (16, "шестнадцать"),
                        (17, "семнадцать"), (18, "восемнадцать"), (19, "девятнадцать"),
                        (20, "двадцать"), (30, "тридцать")]:  # fmt: skip
        add[value] = f"{add.get(value, '')} {word} {word[:-1]}и {word}ю"
    words = {w: (v, "add") for v, ws in add.items() for w in ws.split()}
    words |= dict.fromkeys(["a", "an"], (1, "add"))  # "within a business day" is one
    words |= dict.fromkeys(["hundred", "ratus"], (100, "mul"))
    words |= {"puluh": (10, "mul"), "belas": (10, "teen")}
    big = ["thousand", "mil", "ribu", "тысяча", "тысячи", "тысяч", "тысячу", "тысячей"]
    words |= dict.fromkeys(big, (1000, "big"))
    return words


_WORDS: Final = _number_words()
_WORD: Final = "|".join(sorted(map(re.escape, _WORDS), key=len, reverse=True))
# "and" joins inside one number only after hundred or thousand ("one hundred and five"); "y"
# only after Spanish tens ("treinta y dos"). Anywhere else they join two numbers.
_JOIN: Final = (
    r"(?:[ -]|(?:(?<=hundred)|(?<=thousand))\s+and\s+"
    r"|(?:(?<=treinta)|(?<=cuarenta)|(?<=cincuenta)|(?<=sesenta)|(?<=setenta)|(?<=ochenta)"
    r"|(?<=noventa))\s+y\s+)"
)
_WORD_RUN: Final = re.compile(rf"(?i)(?<!\w)(?:{_WORD})(?:{_JOIN}(?:{_WORD}))*(?!\w)")


def _words_value(run: str) -> int:
    total = current = last = 0
    for word in re.findall(r"\w+", run.lower()):
        if word not in _WORDS:
            continue  # "and", "y"
        value, kind = _WORDS[word]
        if kind == "add":
            current, last = current + value, value
        elif kind == "mul":
            current, last = current - last + (last or 1) * value, 0
        elif kind == "teen":
            current, last = current + value, 0
        else:
            total, current, last = total + (current or 1) * value, 0, 0
    return total + current


def _canonical(d: Decimal) -> str:
    return format(d.normalize(), "f")


def _readings(raw: str) -> set[Decimal] | None:
    """Every value the digits can mean, or None if they are not one number ("1,2,3")."""
    raw = re.sub(r"[\u00a0\u202f ]", "", raw)
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


def _unit_after(text: str, pos: int) -> str | None:
    m = _UNIT_AFTER.match(text, pos)
    return m.lastgroup if m else None


class _Token(NamedTuple):
    start: int
    end: int
    values: frozenset[str]
    unit: str | None
    spelled: bool = False


def _digit_tokens(text: str) -> list[_Token]:
    out: list[_Token] = []
    for m in _NUMBER.finditer(text):
        raw = m.group("num")
        code = next((n for n in _CURRENCY if m.group(f"pre_{n}")), None)
        # "$10" binds tightly; a code yields to a unit after it: "200 USD 2 hours" is hours.
        symbol = code is not None and not _SYMBOL.search(m.group("pre"))
        unit = code if symbol else _unit_after(text, m.end()) or code
        start = m.start("num")
        if _STEP_BEFORE.search(text[max(0, start - 12) : start]):
            continue  # "Step 2" orders the steps; it states nothing
        if unit is None and (
            _UNKNOWN_AFTER.match(text, m.end())
            or _UNKNOWN_BEFORE.search(text[max(0, start - 6) : start])
        ):
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
    # Digits and their multiplier are blanked, so "10 Thousand USD" is not also "thousand USD".
    parts, pos = [], 0
    for t in digits:
        if t.start >= pos:  # the parts of "1,2,3" share one span
            parts += [text[pos : t.start], "\0" * (t.end - t.start)]
            pos = t.end
    out: list[_Token] = []
    for m in _WORD_RUN.finditer("".join([*parts, text[pos:]])):
        values = frozenset({str(_words_value(m.group()))})
        out.append(_Token(m.start(), m.end(), values, _unit_after(text, m.end()), spelled=True))
    return out


def quantities(text: str) -> set[Quantity]:
    """Every number in the text with the unit or currency attached to it. Numbered-list markers
    are formatting, and spelled-out numbers count only before a unit ("one of our agents")."""
    text = _LIST_MARKER.sub(" ", text)
    digits = _digit_tokens(text)
    tokens = sorted([*digits, *_word_tokens(text, digits)])
    for i in range(len(tokens) - 2, -1, -1):
        a, b = tokens[i], tokens[i + 1]
        if a.unit is None and b.unit and _RANGE.fullmatch(text, a.end, b.start):
            tokens[i] = a._replace(unit=b.unit)
    return {
        Quantity(t.values, t.unit)
        for t in tokens
        if t.unit or not t.spelled  # a spelled-out number without a unit is not a claim
    }


def supported(claim: Quantity, evidence: set[Quantity]) -> bool:
    """The same value with the same unit; a bare number is supported only by a bare number, and
    a number with an unknown unit by nothing."""
    return claim.unit != "unknown" and claim in evidence

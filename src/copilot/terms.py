"""Claims without digits that a draft may make only when its sources do.

Links (a URL, an email address, a domain, an @handle) count only verbatim in a cited section or
its page address, compared case-folded. A look-alike fails closed without a confusables table:
a dotted token with a part that mixes Latin and other letters (Latin "valet" with Cyrillic
"ax"), or any token with "://", is a link, and no cited section carries it. Names from closed lists
(currencies, payment methods, messengers, countries, instruments, in English, Russian and
Spanish) count only when a cited section names them too: "yes, in rubles", "we accept Skrill",
"message us on Telegram", "deposits from Nigeria" are claims nobody wrote. The KB itself
names one currency (USD) and one domain; the rest of each list is written by hand. A name off
the lists passes: the drafter's rule 3 and the agent cover it.

Fees, limits and speed are a closed world too: the KB states no fee, no limit other than the
minimum deposit and no withdrawal time, and its only speed words sit in conflicted sections. A
draft that uses a word from one of these lexicons needs a cited section that uses a word from
the same lexicon ("a small processing fee", "a daily withdrawal limit", "within the hour").

`topics` reads whether a sentence is about deposits or withdrawals, so a figure from the deposit
FAQ cannot be stated about withdrawals ("the minimum withdrawal is 8 USD", "the minimum payout").
"""

import re
from typing import Final

_URL: Final = r"\bhttps?://[^\s<>\"'()\[\]]+"
# Every pattern starts only at the start of a token, so no scan restarts inside a long run.
_EMAIL: Final = r"(?<![\w.+-])[\w.+-]+@[\w-]+(?:\.[\w-]+)+"
_HANDLE: Final = r"(?<![\w.+-])@\w{2,}"  # a messenger or social account: the KB names none
# Read on case-folded text; a letter in the first label: "1.Log" is not a domain. The letter is
# a lookahead, not a split of the label, so a run like "a-a-a-" has one way to match.
_DOMAIN: Final = (
    r"(?<![a-z0-9.-])(?:www\.)?(?=[a-z0-9-]*[a-z])[a-z0-9-]+(?:\.[a-z0-9-]+)*\.[a-z]{2,12}\b"
    r"(?:/[^\s<>\"'()\[\]]*)?"
)
# Any scheme in any letters.
_SCHEME: Final = r"(?<![^\s<>\"'()\[\]])[^\s<>\"'()\[\]]+://[^\s<>\"'()\[\]]+"
_LINK: Final = re.compile(rf"{_URL}|{_SCHEME}|{_EMAIL}|{_HANDLE}|{_DOMAIN}")
# Any dotted token, in any script.
_DOTTED: Final = re.compile(r"(?<![\w.-])[\w-]+(?:\.[\w-]+)+")

# Name -> pattern. Codes and signs are case-sensitive ("TRY" is a currency, "try" is not);
# words are not.
_NAMES: Final = {
    # currencies
    "USD": r"\bUSD\b|\$|(?i:\bdollars?\b|\bдоллар\w*|\bd[oó]lar(?:es)?\b)",
    "EUR": r"\bEUR\b|€|(?i:\beuros?\b|\bевро\b)",
    "GBP": r"\bGBP\b|£|(?i:\bpounds? sterling\b|\bфунт\w* стерлинг\w*|\blibras? esterlinas?\b)",
    "RUB": r"\bRUB\b|₽|(?i:\bro?ubles?\b|\bрубл\w*|\brublos?\b)",
    "UAH": r"\bUAH\b|₴|(?i:\bhryvni?as?\b|\bгривн\w*|\bgrivnas?\b)",
    "KZT": r"\bKZT\b|₸|(?i:\btenge\b|\bтенге\b)",
    "INR": r"\bINR\b|₹|(?i:\brupees?\b|\bрупи\w*|\brupias?\b)",
    "IDR": r"\bIDR\b|(?i:\brupiah\b)",
    "NGN": r"\bNGN\b|₦|(?i:\bnairas?\b)",
    "TRY": r"\bTRY\b|₺|(?i:\b(?:turkish )?liras?\b|\bлир[аыу]?\b)",
    "BRL": r"\bBRL\b|R\$",
    "AED": r"\bAED\b|(?i:\bdirhams?\b|\bдирхам\w*|\bd[ií]rhams?\b)",
    "JPY": r"\bJPY\b|¥|(?i:\byen(?:es)?\b|\bиен\w*)",
    "CNY": r"\bCNY\b|(?i:\byuan(?:es)?\b|\bюан\w*)",
    "USDT": r"\bUSDT\b|(?i:\btether\b)",
    "BTC": r"\bBTC\b|(?i:\bbitcoins?\b|\bбиткоин\w*|\bбиткойн\w*)",
    "ETH": r"\bETH\b|(?i:\bethereum\b|\bэфир\w*)",
    # payment methods and networks
    "card": r"(?i:\bcards?\b|\bvisa\b|\bmastercard\b|\bкарт[аеуыойам]\w*|\bкарточк\w*|\btarjetas?\b)",
    "bank transfer": r"\bSWIFT\b|\bSEPA\b|(?i:\b(?:bank|wire) (?:transfer|wire)s?\b|\bбанковск\w* перевод\w*|\btransferencias? bancarias?\b)",
    "e-wallet": r"(?i:\be-?wallets?\b|\bэлектронн\w* кошел\w*|\b(?:billeteras?|monederos?) (?:electr[oó]nic|digital)\w*)",
    "crypto": r"(?i:\bcrypto\w*|\bкрипт\w*|\bcripto\w*)",
    "TRC20/ERC20/BEP20": r"(?i:\b(?:trc|erc|bep)-?20\b)",
    "Skrill": r"(?i:\bskrill\b)",
    "Neteller": r"(?i:\bneteller\b)",
    "PayPal": r"(?i:\bpaypal\b)",
    "Perfect Money": r"(?i:\bperfect ?money\b)",
    "WebMoney": r"(?i:\bweb ?money\b|\bвебмани\b)",
    "FasaPay": r"(?i:\bfasapay\b)",
    "Sticpay": r"(?i:\bsticpay\b)",
    "AdvCash": r"(?i:\badv ?cash\b|\badvanced cash\b)",
    "Payeer": r"(?i:\bpayeer\b)",
    "QIWI": r"(?i:\bqiwi\b|\bкиви\b)",
    "YooMoney": r"(?i:\byoo ?money\b|\bюмани\b|\bюmoney\b)",
    # messengers: the KB names no support channel
    "Telegram": r"(?i:\btelegram\w*|\bтелеграм\w*)",
    "WhatsApp": r"(?i:\bwhats ?app\b|\bватсап\w*|\bвотсап\w*)",
    "Viber": r"(?i:\bviber\b|\bвайбер\w*)",
    "WeChat": r"(?i:\bwe ?chat\b)",
    # countries
    "Nigeria": r"(?i:\bnigeri\w*|\bнигери\w*)",
    "India": r"(?i:\bindia\b|\bинди[яиюей]\b)",
    "Indonesia": r"(?i:\bindonesi\w*|\bиндонези\w*)",
    "Malaysia": r"(?i:\bmalaysi\w*|\bmalasia\b|\bмалайзи\w*)",
    "Vietnam": r"(?i:\bviet ?nam\w*|\bвьетнам\w*)",
    "Thailand": r"(?i:\bthailand\b|\btailandia\b|\bтаиланд\w*)",
    "Pakistan": r"(?i:\bpakist[aá]n\w*|\bпакистан\w*)",
    "Philippines": r"(?i:\bphilippines\b|\bfilipinas\b|\bфилиппин\w*)",
    "Egypt": r"(?i:\begypt\w*|\begipto\b|\bегип[ет]\w*)",
    "Kenya": r"(?i:\bkenya\b|\bkenia\b|\bкени[яиюей]\b)",
    "South Africa": r"(?i:\bsouth africa\w*|\bsud[aá]frica\b|\bюар\b|\bюжн\w* африк\w*)",
    "Russia": r"\bРФ\b|(?i:\brussia\b|\brusia\b|\bросси[яиюей]\b)",
    "Ukraine": r"(?i:\bukrain\w*|\bucrania\b|\bукраин\w*)",
    "Kazakhstan": r"(?i:\bkazakhstan\b|\bkazajist[aá]n\b|\bказахстан\w*)",
    "Belarus": r"(?i:\bbelarus\b|\bbielorrusia\b|\bбеларус\w*|\bбелорусси\w*)",
    "Turkey": r"(?i:\bturkey\b|\btürkiye\b|\bturqu[ií]a\b|\bтурци\w*)",
    "UAE": r"\bUAE\b|\bОАЭ\b|\bEAU\b|(?i:\bemirat\w*|\bэмират\w*|\bdubai\b|\bdub[aá]i\b|\bдубай\w*)",
    "Brazil": r"(?i:\bbrazil\b|\bbrasil\b|\bбразили\w*)",
    "Mexico": r"(?i:\bm[eé]xico\b|\bмексик\w*)",
    "Spain": r"(?i:\bspain\b|\bespaña\b|\bиспани\w*)",
    "United Kingdom": r"\bUK\b|(?i:\bunited kingdom\b|\breino unido\b|\bвеликобритани\w*)",
    "United States": r"\bUSA\b|\bСША\b|(?i:\bunited states\b|\bestados unidos\b|\bee\.? ?uu\.?)",
    "China": r"(?i:\bchina\b|\bкита[йяюе]\w*)",
    "Iran": r"(?i:\bir[aá]n\b|\bиран\w*)",
    "European Union": r"\bEU\b|\bЕС\b|\bUE\b|(?i:\beuropean union\b|\bunión europea\b|\bевросоюз\w*)",
    # instruments
    "gold": r"\bXAU\w*|(?i:\bgold\b|\bзолот\w*|\boro\b)",
    "silver": r"\bXAG\w*|(?i:\bsilver\b|\bсеребр\w*)",
    "oil": r"\bWTI\b|(?i:\boil\b|\bcrude\b|\bbrent\b|\bнефт\w*|\bpetr[oó]leo\b)",
    "stocks and indices": r"\bS&P\b|\bNASDAQ\b|\bUS30\b|\bNAS100\b|\bDAX\b|\bFTSE\b|(?i:\bstocks?\b|\bshares\b|\bindices\b)",
    "currency pair": r"\b[A-Z]{3}/[A-Z]{3}\b",
}
_NAME_PATTERNS: Final = {name: re.compile(p) for name, p in _NAMES.items()}

_TOPICS: Final = {
    "deposit": re.compile(
        r"(?i)\bdeposit\w*|\btop[- ]?ups?\b|\bпополн\w*|\bдепозит\w*|\bвнес\w*|\bdep[oó]sit\w*"
    ),
    "withdrawal": re.compile(
        r"(?i)\bwithdr[ae]w\w*|\bpay ?outs?\b|\bcash(?:ing)? out\b|\btak(?:e|ing|en) out\b"
        r"|\btak(?:e|ing) (?:my |the |your )?(?:money|funds) out\b"
        r"|\bвывод\w*|\bвывест\w*|\bвывел\w*|\bсня[тл]\w*|\bснима\w*|\bretir\w*|\bsac(?:ar|o|a|an|as)\b"
    ),
}

# The closed lexicons of fees, limits and speed, in English, Russian and Spanish, negations and
# "un-/не-/без-" forms included ("unlimited", "безлимитный").
_POLICY_WORDS: Final = {
    "fee": re.compile(
        r"(?i)\bfees?\b|\bcommissions?\b|\bcharge[sd]?\b|\bsurcharges?\b|\bswaps?\b|\bspreads?\b"
        r"|\bcost(?:s|ing)?\b|\bdeduct\w*"
        r"|\bкомисси\w*|\bсвоп\w*|\bспред\w*|\bбесплатн\w*|\bплат[аыуе]\b|\bсбор(?:а|ом|ы|ов)?\b"
        r"|\bcomisi[oó]n\w*|\bcargos?\b|\btarifas?\b|\bgratis\b|\bgratuit\w*|\bcost[eo]s?\b"
    ),
    # The KB states one minimum (the deposit); a minimum never supports a limit or a maximum.
    "minimum": re.compile(r"(?i)\bminim\w*|\bминим\w*|\bm[ií]nim\w*"),
    "limit": re.compile(
        r"(?i)\b(?:un)?limit\w*|\bmax(?:im\w*)?\b|\bcap(?:s|ped)?\b|\bceiling\b|\bup to (?=\d)"
        r"|\bolder than\b|\brestrict\w*"
        r"|\b(?:без ?)?лимит\w*|\b(?:не ?)?ограничен\w*|\bмаксим\w*|\bне (?:старше|более)\b"
        r"|\bl[ií]mite\w*|\bilimitad\w*|\brestricci\w*|\bm[aá]xim\w*|\btope\b|\bhasta (?=\d)"
        r"|\bno (?:m[aá]s|mayor) de\b"
    ),
    "speed": re.compile(
        r"(?i)\binstant\w*|\bimmediate\w*|\bright away\b|\bstraight away\b|\bat once\b"
        r"|\bsame[- ]day\b|\bwithin (?:the|an|one) hour\b|\breal[- ]time\b|\bin no time\b"
        r"|\b(?:a few|a couple of|several) (?:seconds|minutes|hours|days|weeks)\b"
        r"|\bмгновенн\w*|\bмоментальн\w*|\bнемедленн\w*|\bв кратчайш\w*"
        r"|\bв тот же день\b|\bв течение часа\b"
        r"|\b(?:нескольк\w*|пар[уы]) (?:секунд|минут|час\w*|дн\w*|недел\w*)"
        r"|\binmediat\w*|\bal instante\b|\binstant[aá]ne\w*|\bel mismo d[ií]a\b|\ben una hora\b"
        r"|\b(?:unos|unas|algunos|algunas|pocos|pocas) (?:segundos|minutos|horas|d[ií]as|semanas)\b"
    ),
}
# Words that are a speed claim only about money moving: "3 быстрых шага", "сразу после
# регистрации" describe the sign-up, "withdrawals are processed quickly" does not.
_LOOSE_SPEED: Final = re.compile(
    r"(?i)\bquick\w*|\bfast\w*|\bpromptly\b|\bshortly\b|\bsoon\b|\btoday\b|\bright after\b"
    r"|\bбыстр\w*|\bсразу\b|\bоперативн\w*|\bскоро\b|\bсегодня\b"
    r"|\br[aá]pid\w*|\bpronto\b|\bhoy\b|\benseguida\b|\bjusto despu[eé]s\b"
)
# The questions I6 says the KB never answers (docs/kb-issues.md), read on the ticket: a fee
# (a swap, "swap-free" included, is answered by the Islamic-account section), a duration.
_FEE_QUESTION: Final = re.compile(
    r"(?i)\bfees?\b|\bcommissions?\b|\bcharge[sd]?\b|\bcost(?:s|ing)?\b|(?<!swap.)\bfree\b|\bdeduct\w*"
    r"|\bspreads?\b|\bкомисси\w*|\bбесплатн\w*|\bплат[аыуе]\b|\bсбор(?:а|ом|ы|ов)?\b"
    r"|\bcomisi[oó]n\w*|\bcargos?\b|\btarifas?\b|\bgratis\b|\bcost[eo]s?\b"
)
_LEAST: Final = re.compile(r"(?i)\bleast\b|\bhow little\b|\bнаименьш\w*")
_HOW_LONG: Final = re.compile(
    r"(?i)\bhow (?:long|fast|quickly|soon)\b|\bhow many (?:days|hours|minutes)\b|\bwhen will\b"
    r"|\bкак (?:долго|быстро|скоро)\b|\bсколько (?:ид[её]т|времени|дней|часов|ждать)\b"
    r"|\bкогда (?:прид[её]т|придут|поступ\w*|зачисл\w*)"
    r"|\bcu[aá]nto (?:tarda|tiempo|demora)\b|\bcu[aá]ndo (?:llega\w*)"
)
_SENTENCE: Final = re.compile(r"(?<=[.!?;])\s+|\n")


# Ideographic full stops read as dots: "valetax-pay。net" is a domain.
_DOTS: Final = str.maketrans({"\u3002": ".", "\uff61": "."})
_CYRILLIC_TLDS: Final = frozenset(
    {"рф", "рус", "укр", "бел", "срб", "ком", "орг", "онлайн", "сайт"}
)


def _link_key(link: str) -> str:
    """A link as compared: case-folded, no scheme, no "www.", no trailing slash or full stop."""
    key = re.sub(r"^https?://", "", link.casefold().translate(_DOTS)).rstrip("/.,;:!?")
    return key.removeprefix("www.")


def _looks_like_domain(token: str) -> bool:
    """A dotted token outside the ASCII patterns that is still a domain, or a look-alike of one.

    A part mixes Latin and other letters ("valet" + Cyrillic "ax"); or the last part is a Latin
    top-level domain after a part in other letters; or the last part is a Cyrillic one (".рф").
    Words joined by a full stop (a Russian sentence missing its space, an abbreviation) are none
    of these.
    """
    parts = token.split(".")
    latin = [any(c.isascii() and c.isalpha() for c in p) for p in parts]
    other = [any(not c.isascii() and c.isalpha() for c in p) for p in parts]
    last = parts[-1]
    return (
        any(a and b for a, b in zip(latin, other, strict=True))
        or (last.isascii() and last.isalpha() and 2 <= len(last) <= 12 and any(other[:-1]))
        or last in _CYRILLIC_TLDS
    )


def _links(text: str) -> set[str]:
    """Every link in the text, case-folded, look-alikes included."""
    text = text.casefold().translate(_DOTS)
    found = {m.group().rstrip(".,;:!?") for m in _LINK.finditer(text)}
    return found | {m.group() for m in _DOTTED.finditer(text) if _looks_like_domain(m.group())}


def unsupported_links(reply: str, evidence: str) -> list[str]:
    """Links in the reply that are not a link of the evidence, or a path-prefix of one.

    Compared as keys, not as substrings: "valetax.co" is not "valetax.com", and
    "valetax.com/pay" is not under any page of the KB. Look-alikes fail: the KB has none.
    """
    known = {_link_key(link) for link in _links(evidence)}
    return sorted(
        link
        for link in _links(reply)
        if not any(k == _link_key(link) or k.startswith(_link_key(link) + "/") for k in known)
    )


def names(text: str) -> set[str]:
    """Every listed currency, payment method, messenger, country and instrument the text names."""
    return {name for name, pattern in _NAME_PATTERNS.items() if pattern.search(text)}


# Lexicons the KB uses only inside its conflicts: every speed word it has ("instant",
# "immediately") is half of I1, I5 or I7 (docs/kb-issues.md). A draft that makes such a claim
# goes to a person as a conflict whichever section it cites, so the steps that sit next to a
# speed word stay citable.
CONTESTED: Final = frozenset({"speed"})


def sentences(text: str) -> list[str]:
    """The text split at sentence ends and line breaks."""
    return _SENTENCE.split(text)


def policy_words(text: str) -> set[str]:
    """The lexicons the text uses: fee, minimum, limit, speed.

    A loose speed word ("quickly", "сразу", "today") counts only in a sentence about deposits or
    withdrawals; a ticket that asks how long a withdrawal takes is a gap anyway (`kb_gaps`).
    """
    found = {name for name, pattern in _POLICY_WORDS.items() if pattern.search(text)}
    if any(_LOOSE_SPEED.search(s) and topics(s) for s in sentences(text)):
        found.add("speed")
    return found


def topics(text: str) -> set[str]:
    """The topics the text speaks of: deposit, withdrawal."""
    return {name for name, pattern in _TOPICS.items() if pattern.search(text)}


def asked(ticket: str, category: str = "") -> set[str]:
    """The topic the ticket asks about.

    The classifier's category when it is deposit or withdrawal ("I deposited 100 USD, what is
    the least I can take out?" is a withdrawal question), otherwise every topic its words name.
    """
    return {category} if category in _TOPICS else topics(ticket)


def kb_gaps(ticket: str, category: str = "") -> list[str]:
    """What the ticket asks that no KB section answers (I6): a person answers it.

    Fees, a deposit or withdrawal limit, the minimum withdrawal, how long a withdrawal takes.
    Read on the ticket, so no wording of the draft can answer it.
    """
    on = asked(ticket, category)
    gaps = {
        "fees": bool(_FEE_QUESTION.search(ticket)),
        "deposit or withdrawal limits": bool(on) and bool(_POLICY_WORDS["limit"].search(ticket)),
        "the minimum withdrawal": "withdrawal" in on
        and bool(_POLICY_WORDS["minimum"].search(ticket) or _LEAST.search(ticket)),
        "the withdrawal time": "withdrawal" in on
        and bool(_HOW_LONG.search(ticket) or "speed" in policy_words(ticket)),
    }
    return [gap for gap, hit in gaps.items() if hit]

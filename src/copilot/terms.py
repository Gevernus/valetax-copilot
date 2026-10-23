"""Claims without digits that a draft may make only when its sources do.

Links (a URL, an email address, a domain) count only verbatim in a cited section or its page
address. Names from closed lists (currencies, payment methods, countries, instruments, in
English, Russian and Spanish) count only when a cited section names them too: "yes, in
rubles", "we accept Skrill", "deposits from Nigeria" are claims nobody wrote. The KB itself
names one currency (USD) and one domain; the rest of each list is written by hand. A name off
the lists passes: the drafter's rule 3 and the agent cover it.

`topics` reads whether a sentence is about deposits or withdrawals, so a figure from the deposit
FAQ cannot be stated about withdrawals ("the minimum withdrawal is 8 USD").
"""

import re
from typing import Final

_URL: Final = r"\bhttps?://[^\s<>\"'()\[\]]+"
_EMAIL: Final = r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+"
# Lower case only, a letter in the first label: "Member.Area" or "1.Log" is not a domain.
_DOMAIN: Final = (
    r"\b(?:www\.)?[a-z0-9-]*[a-z][a-z0-9-]*(?:\.[a-z0-9-]+)*\.[a-z]{2,12}\b(?:/[^\s<>\"'()\[\]]*)?"
)
_LINK: Final = re.compile(rf"{_URL}|{_EMAIL}|{_DOMAIN}")

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
    "deposit": re.compile(r"(?i)\bdeposit\w*|\bпополн\w*|\bдепозит\w*|\bвнес\w*|\bdep[oó]sit\w*"),
    "withdrawal": re.compile(r"(?i)\bwithdr[ae]w\w*|\bвывод\w*|\bвывест\w*|\bвывел\w*|\bretir\w*"),
}


def _link_key(link: str) -> str:
    """A link as compared: lower case, without the scheme or a trailing slash or full stop."""
    return re.sub(r"^https?://", "", link.lower()).rstrip("/.,;:!?")


def unsupported_links(reply: str, evidence: str) -> list[str]:
    """Links in the reply that the evidence does not carry verbatim."""
    found = {m.group().rstrip(".,;:!?") for m in _LINK.finditer(reply)}
    return sorted(link for link in found if _link_key(link) not in evidence.lower())


def names(text: str) -> set[str]:
    """Every listed currency, payment method, country and instrument the text names."""
    return {name for name, pattern in _NAME_PATTERNS.items() if pattern.search(text)}


def topics(text: str) -> set[str]:
    """The topics the text speaks of: deposit, withdrawal."""
    return {name for name, pattern in _TOPICS.items() if pattern.search(text)}

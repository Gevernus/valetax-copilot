import pytest

from copilot.quantities import Quantity, quantities, supported


def q(*values: str, unit: str | None = None) -> Quantity:
    return Quantity(frozenset(values), unit)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("8 USD", q("8", unit="usd")),
        ("8.00 USD", q("8", unit="usd")),
        ("8,0 USD", q("8", unit="usd")),
        ("10 USDT", q("10", unit="usdt")),
        ("10%", q("10", unit="percent")),
        ("1 000 USD", q("1000", unit="usd")),
        ("1\u00a0000 USD", q("1000", unit="usd")),
        ("1.000,50 EUR", q("1000.5", unit="eur")),
        ("1,000.50 USD", q("1000.5", unit="usd")),
        ("1,000,000 USD", q("1000000", unit="usd")),
        ("48 hours", q("48", unit="hour")),
        ("48h", q("48", unit="hour")),
        ("a 24-hour window", q("24", unit="hour")),
        ("60 минут", q("60", unit="minute")),
        ("48 часов", q("48", unit="hour")),
        ("6 meses", q("6", unit="month")),
        ("3 business days", q("3", unit="business_day")),
        ("3 рабочих дня", q("3", unit="business_day")),
        ("up to 1:2000", q("1:2000")),
    ],
)
def test_digits_with_their_unit(text: str, expected: Quantity) -> None:
    assert quantities(text) == {expected}


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        # Symbols and codes, before or after the number, spaced or glued.
        ("$10", q("10", unit="usd")),
        ("$ 10", q("10", unit="usd")),
        ("10 $", q("10", unit="usd")),
        ("10$", q("10", unit="usd")),
        ("USD 10", q("10", unit="usd")),
        ("USD500", q("500", unit="usd")),
        ("The minimum deposit is USD500.", q("500", unit="usd")),
        ("USDT10", q("10", unit="usdt")),
        ("EUR50", q("50", unit="eur")),
        ("8 €", q("8", unit="eur")),
        ("de 8 €.", q("8", unit="eur")),
        ("8€", q("8", unit="eur")),
        ("8 euros", q("8", unit="eur")),
        ("100 рублей", q("100", unit="rub")),
        ("500 ₽", q("500", unit="rub")),
        ("Rp 50", q("50", unit="idr")),
    ],
)
def test_currency_in_any_position(text: str, expected: Quantity) -> None:
    assert quantities(text) == {expected}


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("$10k", q("10000", unit="usd")),
        ("50 тысяч рублей", q("50000", unit="rub")),
        ("вывел 50 тысяч рублей", q("50000", unit="rub")),
        ("10 тыс. USD", q("10000", unit="usd")),
        ("10 тыс", q("10000")),
        ("2 миллиона", q("2000000")),
        ("1 млн", q("1000000")),
        ("5 thousand", q("5000")),
        ("10 Thousand USD", q("10000", unit="usd")),
        ("5 mil", q("5000")),
        ("3 juta", q("3000000")),
    ],
)
def test_multiplier_words(text: str, expected: Quantity) -> None:
    assert quantities(text) == {expected}


def test_a_unit_after_the_number_wins_over_a_currency_code_before_it() -> None:
    assert quantities("I deposited 200 USD 2 hours ago") == {
        q("200", unit="usd"),
        q("2", unit="hour"),
    }


def test_thousands_separator_is_not_read_as_a_small_number() -> None:
    (amount,) = quantities("$1,000")
    assert "1000" in amount.values
    assert amount != q("1", unit="usd")


def test_ambiguous_separator_keeps_both_readings() -> None:
    # "1,000" is a thousand in English and one in Russian or Spanish; "1.000" the other way round.
    assert quantities("1,000 USD") == {q("1000", "1", unit="usd")}
    assert quantities("1.000 USD") == {q("1000", "1", unit="usd")}
    # A leading zero or a fraction that is not three digits long is a decimal everywhere.
    assert quantities("0,500 lots") == {q("0.5", unit="lot")}
    assert quantities("1,5 lots") == {q("1.5", unit="lot")}


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("two business days", q("2", unit="business_day")),
        ("twenty-four hours", q("24", unit="hour")),
        ("one hundred dollars", q("100", unit="usd")),
        ("one hundred and five dollars", q("105", unit="usd")),
        ("в течение двух рабочих дней", q("2", unit="business_day")),
        ("сорок восемь часов", q("48", unit="hour")),
        ("тысяча долларов", q("1000", unit="usd")),
        ("dos días hábiles", q("2", unit="business_day")),
        ("treinta y dos horas", q("32", unit="hour")),
        ("veinticuatro horas", q("24", unit="hour")),
        ("dua puluh empat jam", q("24", unit="hour")),
        ("dua belas hari", q("12", unit="day")),
        ("seratus USD", q("100", unit="usd")),
    ],
)
def test_number_words_before_a_unit(text: str, expected: Quantity) -> None:
    assert quantities(text) == {expected}


def test_number_words_without_a_unit_are_not_claims() -> None:
    assert quantities("one of our agents will check it") == set()
    assert quantities("один из шагов") == set()


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("1-2 business days", {q("1", unit="business_day"), q("2", unit="business_day")}),
        ("1 to 3 days", {q("1", unit="day"), q("3", unit="day")}),
        ("two to three business days", {q("2", unit="business_day"), q("3", unit="business_day")}),
        # "и", "and", "y" join two numbers here; they are not one number.
        ("два и три дня", {q("2", unit="day"), q("3", unit="day")}),
        ("dos y tres días", {q("2", unit="day"), q("3", unit="day")}),
        ("1 hour to 2 days", {q("1", unit="hour"), q("2", unit="day")}),
    ],
)
def test_a_range_binds_the_unit_to_both_ends(text: str, expected: set[Quantity]) -> None:
    assert quantities(text) == expected


def test_list_markers_and_numbers_inside_words_are_skipped() -> None:
    assert quantities("1. Log in.\n2. Select MT5 or TRC20.") == set()


def test_a_number_is_supported_only_with_its_unit() -> None:
    evidence = quantities("Completed within 48 hours. Open an account in 3 simple steps.")
    assert supported(q("48", unit="hour"), evidence)
    assert supported(q("3"), evidence)
    assert not supported(q("48", unit="day"), evidence)
    assert not supported(q("3", unit="day"), evidence)
    # A bare number is a different claim from the same value with a unit: "8" vs "8 USD".
    assert not supported(q("48"), evidence)


def test_currencies_and_percent_do_not_stand_in_for_each_other() -> None:
    evidence = quantities("The minimum deposit starts from 10 USD.")
    assert supported(q("10", unit="usd"), evidence)
    assert not supported(q("10", unit="usdt"), evidence)
    assert not supported(q("10", unit="eur"), evidence)
    assert not supported(q("10", unit="percent"), evidence)


def test_ambiguous_number_needs_the_same_readings() -> None:
    assert not supported(q("1000", "1", unit="usd"), quantities("$1"))
    assert not supported(q("1000", "1", unit="usd"), quantities("1000 USD"))
    assert supported(q("1000", "1", unit="usd"), quantities("1.000 USD"))


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("within a business day", q("1", unit="business_day")),
        ("in an hour", q("1", unit="hour")),
        ("one day", q("1", unit="day")),
        ("en un día", q("1", unit="day")),
        ("через один день", q("1", unit="day")),
    ],
)
def test_an_article_before_a_unit_is_one(text: str, expected: Quantity) -> None:
    assert quantities(text) == {expected}


@pytest.mark.parametrize(
    "text",
    [
        "Min. deposit",
        "Good day, thanks for your message.",
        "Buenos días, gracias.",
        "Нужно добавить документ. Добро пожаловать!",
        "Bây giờ bạn có thể nạp tiền.",
        "您今天可以登录会员区。",
        "周末也可以提交。",
        "بشكل عام، يمكنك الإيداع.",
        "Silakan kirim dokumen hari ini.",
        "часто задаваемые вопросы",
    ],
)
def test_a_unit_word_alone_is_not_a_claim(text: str) -> None:
    assert quantities(text) == set()


@pytest.mark.parametrize(
    "text",
    [
        "A fee of 2 AUD applies.",
        "The minimum deposit is 3 BTC.",
        "Withdrawals over 4 INR need extra documents.",
        "The minimum is ₹2.",
        "A withdrawal fee of 3 ₹ applies.",
        "Account opening takes up to 4 working hours.",
        "Deposits are credited within 2 trading days.",
        "You can withdraw up to 4 lakh per day.",
        "about 2 billion VND",
    ],
)
def test_a_number_with_an_unknown_unit_is_never_supported(text: str) -> None:
    claims = quantities(text)
    assert claims
    assert all(q.unit == "unknown" for q in claims)
    assert not any(supported(c, claims) for c in claims)


def test_step_numbers_and_list_markers_are_not_claims() -> None:
    assert quantities("Step 1: Log in. Step 2: Select. Шаг 3: готово. Paso 4.") == set()
    assert quantities("To deposit: 1. Log in. 2. Select a channel. 3) Enter the amount.") == set()


def test_billions() -> None:
    assert quantities("2 billion USD") == {q("2000000000", unit="usd")}
    assert quantities("3 млрд рублей") == {q("3000000000", unit="rub")}


@pytest.mark.parametrize(
    ("quantity", "text"),
    [
        (q("3", unit="day"), "3 days"),
        (q("1", unit="business_day"), "1 business day"),
        (q("1000", "1", unit="usd"), "1 or 1000 USD"),
        (q("10", unit="percent"), "10%"),
        (q("1:2000"), "1:2000"),
    ],
)
def test_quantities_read_as_text(quantity: Quantity, text: str) -> None:
    assert str(quantity) == text


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("trong vòng 60 phút.", q("60", unit="minute")),
        ("在60分钟内", q("60", unit="minute")),
        ("存款60美元", q("60", unit="usd")),
        ("من 8 USD، ويعتمد", q("8", unit="usd")),
        ("خلال 48 ساعة", q("48", unit="hour")),
        ("48 Stunden", q("48", unit="hour")),
        ("48 heures", q("48", unit="hour")),
        ("48 saat içinde", q("48", unit="hour")),
        ("en fazla 6 aylık olması", q("6", unit="month")),
        ("3 iş günü içinde", q("3", unit="business_day")),
        ("3 dias úteis", q("3", unit="business_day")),
        ("6 місяців", q("6", unit="month")),
        ("48 घंटे", q("48", unit="hour")),
        ("60 นาที", q("60", unit="minute")),
    ],
)
def test_units_in_every_detected_language(text: str, expected: Quantity) -> None:
    # A unit the parser cannot read leaves the number bare, and a bare number does not match
    # "8 USD"; so every language `language.py` can return needs its units here.
    assert quantities(text) == {expected}

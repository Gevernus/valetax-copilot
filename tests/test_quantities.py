import pytest

from copilot.quantities import Quantity, quantities, supported, time_units


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


def test_a_number_is_supported_only_with_its_unit() -> None:
    evidence = quantities("Completed within 48 hours. Open an account in 3 simple steps.")
    assert supported(q("48", unit="hour"), evidence)
    assert supported(q("3", unit="steps"), evidence)
    assert not supported(q("3"), evidence)  # a step count supports only a step count
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
        "The fee is 3 pounds.",
        "3 Pfund",
        "a 2 percentage-point fee",
        "Withdrawals take 2 cycles.",
        "存款手续费为3英镑。",
        "ค่าธรรมเนียมการฝาก 2 ปอนด์",
        "存款将在3个钟头内到账。",
        "3  pounds",
        "3 more pounds",
        # Next to a step word, a number with an unknown unit is still unknown, not a step.
        "The fee is 3 AUD per step.",
        "A fee of 2 pounds per step applies.",
        "Комиссия 2 фунта за шаг.",
        "Step 2 – 3 AUD is the minimum for this channel.",
        "Step 4 - 2 pounds fee is charged.",
        "Шаг 2 — 3 фунта комиссии за пополнение.",
        "Step 3 – 4 minimum.",
        "Step 1 to 4 AUD.",
        "Paso 2 - 3 libras de comisión.",
        "Steps 1-4 AUD.",
        "Steps 2–3: 4 minimum.",
        "Шаг 2 до 3 фунтов минимум.",
    ],
)
def test_a_number_with_an_unknown_unit_is_never_supported(text: str) -> None:
    unknown = {c for c in quantities(text) if c.unit != "step"}
    assert unknown
    assert {c.unit for c in unknown} == {"unknown"}
    assert not any(supported(c, quantities(text)) for c in unknown)


def test_a_ratio_carries_no_unit() -> None:
    assert quantities("up to 1:2000 depending on account types") == {q("1:2000")}
    assert quantities("We offer 1:2000 leverage on 1:500 accounts.") == {q("1:2000"), q("1:500")}


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("To deposit: 1. Log in. 2. Select a channel. 3) Enter the amount.", set()),
        ("1. Log in.\n2. Select MT5 or TRC20.", set()),
        ("Чтобы пополнить счёт: 1) войдите; 2) выберите способ; 3) введите сумму.", set()),
        # After ";" a list continues only if it was already running on ";" or ":".
        ("1. Log in. 2. Pick a channel. Minimum deposit; 3. Done.", {q("3")}),
        ("Fee:\n\n\n2. Next.", {q("2")}),
        # A list is a sequence from 1, never after "("; a marker after ":" may only start one.
        ("Minimum deposit: 5. You can fund via any channel.", {q("5")}),
        ("Withdrawal fee: 2. It is charged on every withdrawal.", {q("2")}),
        ("Комиссия за вывод: 2. Она взимается с каждого вывода.", {q("2")}),
        ("The fee is (3) per withdrawal.", {q("3")}),
        ("Fee: 1. It is charged on every withdrawal.", {q("1")}),
        (
            "1. Log in to your Member Area. 2. Select a channel. 3. Enter the amount. "
            "Minimum deposit: 4. Happy trading!",
            {q("4")},
        ),
        ("Withdrawal fee: 1. Minimum deposit: 2. Have a nice day.", {q("1"), q("2")}),
        ("Минимальный депозит: 1. Комиссия: 2. Хорошего дня!", {q("1"), q("2")}),
        ("The fee is 1) per deposit and 2) per withdrawal.", {q("1"), q("2")}),
        (
            "The minimum deposit starts from 8 USD. 1. Log in. 2. Fee: 3. Done.",
            {q("8", unit="usd"), q("3")},
        ),
    ],
)
def test_list_markers_are_a_sequence(text: str, expected: set[Quantity]) -> None:
    assert quantities(text) == expected


@pytest.mark.parametrize(
    ("text", "units"),
    [
        ("Вывод средств обрабатывается в течение часа.", {"hour"}),
        ("Withdrawals are processed within the hour.", {"hour"}),
        ("Withdrawals are processed the same business day.", {"business_day", "day"}),
        ("Вывод придёт через неделю.", {"week"}),
        ("Вывод обрабатывается за сутки.", {"day"}),
        ("提款将在一小时内处理。", {"hour"}),
        ("Les retraits sont traités en une heure.", {"hour"}),
        ("Auszahlungen werden innerhalb einer Stunde bearbeitet.", {"hour"}),
        ("Withdrawals usually take a couple of days.", {"day"}),
        ("El retiro se procesa en una hora.", {"hour"}),
        ("Penarikan diproses dalam sehari.", {"day"}),
        ("Para çekme işlemi bir saat içinde tamamlanır.", {"hour"}),
        ("تتم معالجة السحب خلال ساعة.", {"hour"}),
        ("Rút tiền được xử lý trong một giờ.", {"hour"}),
        ("Rút tiền mất trong hai ngày.", {"day"}),
        ("निकासी एक घंटे में संसाधित होती है।", {"hour"}),
        ("Вывод займёт полчаса.", {"hour"}),
        ("в течение получаса", {"hour"}),
        ("Le retrait est traité dans la journée.", {"day"}),
        ("Die Auszahlung erfolgt am selben Tag.", {"day"}),
        ("innerhalb eines Tages", {"day"}),
        ("تتم معالجة السحب في نفس اليوم.", {"day"}),
        ("تتم معالجة السحب خلال الساعة.", {"hour"}),
        ("تتم معالجة السحب في اليوم التالي.", {"day"}),
        ("تتم معالجة السحب خلال الأسبوع.", {"week"}),
        ("تصل الأموال خلال الشهر.", {"month"}),
        ("تتم معالجة السحب خلال الساعات القادمة.", {"hour"}),
        ("تتم معالجة السحب خلال اليوم.", {"day"}),
        ("تتم معالجة السحب في ذات اليوم.", {"day"}),
        ("تصل الأموال بحلول نهاية اليوم.", {"day"}),
        ("يتم ذلك خلال الدقائق القادمة.", {"minute"}),
        ("يتم ذلك خلال السنة.", {"year"}),
    ],
)
def test_a_time_unit_without_digits_is_still_a_claim(text: str, units: set[str]) -> None:
    assert time_units(text) == units


@pytest.mark.parametrize(
    "text",
    [
        "Good day, thanks for your message.",
        "Have a nice day!",
        "Buenos días, gracias por escribirnos.",
        "Добрый день! Добро пожаловать.",
        "Нужно добавить документ.",
        "Bây giờ bạn có thể nạp tiền.",
        "您今天可以登录会员区。",
        "周末也可以提交。",
        "بشكل عام، يمكنك الإيداع.",
        "Silakan kirim dokumen hari ini.",
        "Support is available 24/7.",
        "Puede depositar a cualquier hora.",
        "Min. deposit",
        "Wait a minute, please.",
        "Guten Tag!",
        "Bonne journée !",
        "Bao giờ bạn cần?",
        "يمكنك الإيداع اليوم.",
        "часто задаваемые вопросы",
        "Нужно добавить документ. Добро пожаловать!",
    ],
)
def test_greetings_and_idioms_are_not_claims(text: str) -> None:
    assert time_units(text) == set()
    assert quantities(text) == set()


def test_a_rate_is_not_a_time_claim() -> None:
    assert time_units("Support works 24 hours a day.") == set()


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
    # A unit the tables cannot read makes the number unsupported, so every language
    # `language.py` can return needs its units here.
    assert quantities(text) == {expected}


@pytest.mark.xfail(
    strict=True,
    reason="known limit: a time without a digit in Chinese or Thai, written with a numeral word "
    "or without a separate unit word, is not read (decisions.md §8)",
)
@pytest.mark.parametrize(
    "text",
    [
        "一天内到账。",
        "三天内处理。",
        "一周内处理。",
        "当天处理。",
        "次日到账。",
        "ภายในหนึ่งวัน",
        "ภายในวันเดียวกัน",
    ],
)
def test_digitless_chinese_and_thai_timelines(text: str) -> None:
    assert time_units(text)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Step 2: Select a channel.", {q("2", unit="step")}),
        ("Шаг 3: готово.", {q("3", unit="step")}),
        ("الخطوة 1: سجل الدخول", {q("1", unit="step")}),
        ("第1步：登录", {q("1", unit="step")}),
        ("ขั้นตอนที่ 1 เข้าสู่ระบบ", {q("1", unit="step")}),
        ("चरण 1: लॉग इन करें", {q("1", unit="step")}),
        ("Крок 1: увійдіть", {q("1", unit="step")}),
        ("the 1st step", {q("1", unit="step")}),
        ("2-й шаг: выберите способ оплаты", {q("2", unit="step")}),
        ("Step #2: select", {q("2", unit="step")}),
        ("Шаг №2: выберите", {q("2", unit="step")}),
        ("Bước thứ 2: chọn kênh", {q("2", unit="step")}),
        ("Langkah ke-2: pilih saluran", {q("2", unit="step")}),
        ("Follow steps 1-4 below.", {q("1", unit="step"), q("4", unit="step")}),
        ("Шаги 1–4 описаны ниже.", {q("1", unit="step"), q("4", unit="step")}),
        ("Steps 2 – 3 are below.", {q("2", unit="step"), q("3", unit="step")}),
        # A count of steps is a different claim from a step's number.
        ("in 3 simple steps", {q("3", unit="steps")}),
        ("in 3 quick and simple steps", {q("3", unit="steps")}),
        ("в 3 простых шага", {q("3", unit="steps")}),
        ("3 steps", {q("3", unit="steps")}),
    ],
)
def test_step_numbers_and_step_counts(text: str, expected: set[Quantity]) -> None:
    assert quantities(text) == expected


def test_step_and_unknown_read_as_text() -> None:
    assert str(q("2", unit="step")) == "step 2"
    assert str(q("3", unit="steps")) == "3 steps"
    assert str(q("3", unit="unknown")) == "3 (unit not recognised)"

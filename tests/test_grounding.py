import pytest

from copilot.draft import Draft
from copilot.grounding import check_draft
from copilot.kb import KnowledgeBase, load_kb


@pytest.fixture(scope="module")
def kb() -> KnowledgeBase:
    return load_kb()


def draft(reply: str, *citations: str) -> Draft:
    return Draft(abstain=False, reply=reply, citations=list(citations))


def test_number_from_cited_section_passes(kb: KnowledgeBase) -> None:
    d = draft(
        "The minimum deposit starts from 8 USD, depending on the account type.",
        "funding.min-deposit",
    )
    assert check_draft(d, kb, "what is the minimum deposit?").ok


def test_number_not_in_cited_section_fails(kb: KnowledgeBase) -> None:
    d = draft("The minimum deposit is 10 USD.", "funding.min-deposit")
    result = check_draft(d, kb, "what is the minimum deposit?")
    assert not result.ok
    assert "10 USD" in result.problems[0]


def test_number_from_an_uncited_section_fails(kb: KnowledgeBase) -> None:
    # 48 hours is in open.time, but the draft cites only the deposit FAQ.
    d = draft("Verification takes 48 hours.", "funding.min-deposit")
    assert not check_draft(d, kb, "how long is verification?").ok


def test_number_echoed_from_ticket_is_shown_but_marked(kb: KnowledgeBase) -> None:
    d = draft(
        "Your request from 3 days ago is in queue and in the midst of getting processed.",
        "funding.withdrawal-pending",
    )
    result = check_draft(d, kb, "my withdrawal is pending for 3 days")
    assert result.ok
    assert result.client_figures == ("3 days",)


def test_ticket_does_not_support_a_policy_figure(kb: KnowledgeBase) -> None:
    # The ticket says "3 days ago"; "3 business days" is a processing time nobody stated.
    d = draft("Withdrawals are processed within 3 business days.", "funding.withdrawal-pending")
    result = check_draft(d, kb, "I requested a withdrawal 3 days ago")
    assert not result.ok
    assert any("3 business days" in p for p in result.problems)


def test_thousands_are_not_supported_by_a_one(kb: KnowledgeBase) -> None:
    d = draft("The minimum deposit starts from $1,000.", "funding.min-deposit")
    assert not check_draft(d, kb, "minimum deposit? I have $1 left").ok


def test_spelled_out_number_is_checked(kb: KnowledgeBase) -> None:
    d = draft("Withdrawals take two business days.", "funding.withdrawal-pending")
    assert not check_draft(d, kb, "how long do withdrawals take?").ok


def test_number_bound_to_another_unit_fails(kb: KnowledgeBase) -> None:
    # 48 is in open.time, as hours.
    d = draft("Verification is completed within 48 days.", "open.time")
    assert not check_draft(d, kb, "how long is verification?").ok


def test_policy_claim_echoed_from_ticket_is_marked(kb: KnowledgeBase) -> None:
    d = draft("Deposits are free of charge.", "funding.how-to-deposit")
    result = check_draft(d, kb, "your agent said deposits are free of charge, right?")
    assert result.ok
    assert result.client_figures == ("free of charge",)


def test_invented_time_without_a_digit_fails(kb: KnowledgeBase) -> None:
    d = draft(
        "Withdrawals are usually processed within a business day.", "funding.withdrawal-pending"
    )
    result = check_draft(d, kb, "how long do withdrawals take?")
    assert any("time units" in p and "business days" in p for p in result.problems)


def test_time_unit_in_other_language_is_matched(kb: KnowledgeBase) -> None:
    d = draft("Баланс обновится в течение 60 минут.", "funding.credit-time")
    assert check_draft(d, kb, "когда зачислят депозит?").ok


def test_fee_claim_fails(kb: KnowledgeBase) -> None:
    d = draft("Deposits are free of charge.", "funding.how-to-deposit")
    assert not check_draft(d, kb, "are there fees?").ok


def test_unknown_or_missing_citation_fails(kb: KnowledgeBase) -> None:
    assert not check_draft(draft("Hello."), kb, "hi").ok
    assert not check_draft(draft("Hello.", "no.such-section"), kb, "hi").ok


def test_trading_advice_in_reply_fails(kb: KnowledgeBase) -> None:
    d = draft("We recommend you buy gold while it is low.", "open.leverage")
    assert not check_draft(d, kb, "should I buy gold?").ok


def test_numbered_list_is_not_a_claim(kb: KnowledgeBase) -> None:
    d = draft(
        "1. Log in to your member area.\n2. Select the preferred payment option.",
        "funding.how-to-deposit",
    )
    assert check_draft(d, kb, "how do I deposit?").ok


def test_abstention_passes(kb: KnowledgeBase) -> None:
    d = Draft(abstain=True, abstain_reason="fees are not in the knowledge base")
    assert check_draft(d, kb, "what are the fees?").ok


@pytest.mark.parametrize(
    "reply",
    [
        "The minimum deposit is USD500.",
        "El depósito mínimo es de 8 €.",
        "The minimum deposit is 8 USDT.",
        "The minimum deposit starts from 8.",  # the source says 8 USD
    ],
)
def test_currency_must_match_the_source(kb: KnowledgeBase, reply: str) -> None:
    assert not check_draft(draft(reply, "funding.min-deposit"), kb, "minimum deposit?").ok


@pytest.mark.parametrize(
    ("reply", "citations"),
    [
        ("A fee of 2 AUD applies to each deposit.", ["deposit.steps"]),
        ("The minimum deposit is 3 BTC.", ["deposit.steps"]),
        ("Account opening takes up to 4 working hours.", ["open.steps", "open.time"]),
        ("The fee is 3 pounds.", ["open.steps"]),
        ("Deposits are credited within a business day.", ["funding.credit-time"]),
        ("Вывод средств обрабатывается в течение часа.", ["funding.withdrawal-pending"]),
        ("Withdrawals are processed the same business day.", ["funding.withdrawal-pending"]),
        ("提款将在一小时内处理。", ["funding.withdrawal-pending"]),
        ("Withdrawals usually take a couple of days.", ["funding.withdrawal-pending"]),
    ],
)
def test_invented_amounts_and_timelines_are_withheld(
    kb: KnowledgeBase, reply: str, citations: list[str]
) -> None:
    assert not check_draft(draft(reply, *citations), kb, "question").ok


@pytest.mark.parametrize(
    "reply",
    [
        "Step 1: Log in to your Member Area. Step 2: Select your preferred payment channel.",
        "الخطوة 1: سجل الدخول. الخطوة 2: اختر قناة الدفع.",
        "第1步：登录会员区。第2步：选择付款渠道。",
        "Крок 1: увійдіть до кабінету. Крок 2: оберіть канал.",
        "चरण 1: लॉग इन करें। चरण 2: भुगतान चैनल चुनें।",
        "ขั้นตอนที่ 1 เข้าสู่ระบบ ขั้นตอนที่ 2 เลือกช่องทาง",
        "The 1st step is to log in; the 2nd step is to pick a channel.",
        "Шаг 1: войдите. Шаг 2: выберите канал.",
        "Follow steps 1-4 below.",
        "Шаги 1–4 описаны ниже.",
        "Step #2: Select your preferred payment channel.",
        "Шаг №2: выберите способ оплаты.",
        "Bước thứ 2: chọn kênh thanh toán.",
        "Langkah ke-2: pilih saluran pembayaran.",
        "2-й шаг: выберите способ оплаты.",
        "Paso 2: seleccione su canal de pago preferido.",
        "In step 2, select your preferred payment channel.",
    ],
)
def test_step_lists_in_any_language_pass(kb: KnowledgeBase, reply: str) -> None:
    assert check_draft(draft(reply, "deposit.steps"), kb, "how do I deposit?").ok


@pytest.mark.parametrize(
    "reply",
    [
        "Добро пожаловать! Чтобы добавить способ оплаты, войдите в личный кабинет.",
        "Buenos días. Puede depositar desde el Área de miembros.",
        "Good day, thanks for your message. You may log in to your member area to deposit.",
    ],
)
def test_greetings_are_not_time_claims(kb: KnowledgeBase, reply: str) -> None:
    assert check_draft(draft(reply, "funding.how-to-deposit"), kb, "how to deposit?").ok


def test_open_steps_count_is_supported(kb: KnowledgeBase) -> None:
    d = draft("You can open an account in 3 simple steps.", "open.steps")
    assert check_draft(d, kb, "how do I open an account?").ok


@pytest.mark.parametrize(
    "reply",
    [
        "Our 24/7 support team can help. The minimum deposit starts from 8 USD.",
        "Log in to MT5 and enable 2FA. The minimum deposit starts from 8 USD.",
        "Your card must support 3DS. The minimum deposit starts from 8 USD.",
    ],
)
def test_product_names_with_digits_are_not_claims(kb: KnowledgeBase, reply: str) -> None:
    assert check_draft(draft(reply, "funding.min-deposit"), kb, "min deposit?").ok


def test_a_figure_that_looks_like_a_list_number_is_checked(kb: KnowledgeBase) -> None:
    d = draft("Minimum deposit: 5. You can fund via any channel.", "funding.min-deposit")
    assert not check_draft(d, kb, "minimum deposit?").ok

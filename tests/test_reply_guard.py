import pytest
from evals.run_drafts import load_drafts

from copilot.reply_guard import GUARDS, check_reply
from copilot.routing import Reason


@pytest.mark.parametrize(
    ("reply", "reason"),
    [
        ("Your account has been verified now.", Reason.RESERVED_WORDING),
        ("Your withdrawal has been rejected.", Reason.RESERVED_WORDING),
        ("Your account is verified.", Reason.RESERVED_WORDING),
        ("We've successfully verified your account.", Reason.RESERVED_WORDING),
        ("Your withdrawal is now approved.", Reason.RESERVED_WORDING),
        (
            "After reviewing your documents, we have approved your withdrawal.",
            Reason.RESERVED_WORDING,
        ),
        ("When you wrote, it was already approved.", Reason.RESERVED_WORDING),
        ("Мы одобрили вашу заявку.", Reason.RESERVED_WORDING),
        ("Ваш счёт разблокирован.", Reason.RESERVED_WORDING),
        ("Мы вернём вам средства.", Reason.RESERVED_WORDING),
        ("Su retiro fue aprobado.", Reason.RESERVED_WORDING),
        ("Hemos aprobado su solicitud.", Reason.RESERVED_WORDING),
        ("Your account is under compliance review.", Reason.TIPPING_OFF),
        ("This is part of an AML check.", Reason.TIPPING_OFF),
        ("Ваш счёт проверяет служба безопасности.", Reason.TIPPING_OFF),
        ("Estamos revisando el origen de sus fondos.", Reason.TIPPING_OFF),
        ("Your case has been passed to the responsible team.", Reason.RESERVED_WORDING),
        ("We have forwarded your request.", Reason.RESERVED_WORDING),
        ("Ваша жалоба передана ответственной команде.", Reason.RESERVED_WORDING),
        ("Hemos trasladado su caso.", Reason.RESERVED_WORDING),
    ],
)
def test_plain_wordings_are_caught_by_the_patterns(reply: str, reason: Reason) -> None:
    result = check_reply(reply, None, 0.5)
    assert reason in result.reasons
    assert result.record == {"status": "patterns only"}


@pytest.mark.parametrize(
    "reply",
    [
        "Once it is approved, you will be notified.",
        "Как только запрос будет одобрен, вы получите уведомление.",
        "A verification code is sent to your email.",
        "Если вы уже передали документы, дождитесь письма.",
        "We protect every account against identity theft and fraud.",
    ],
)
def test_the_patterns_leave_help_page_wording_alone(reply: str) -> None:
    assert check_reply(reply, None, 0.5).problems == ()


def test_patterns_raise_no_false_alarm_on_the_dev_drafts() -> None:
    # The patterns are a frozen, precise floor; the REPLY questions take the paraphrases.
    # Only dev rows: the holdout measures, it is not a test fixture.
    false_alarms = [
        (row["id"], label)
        for row in load_drafts()
        if row["split"] == "dev"
        for label, guard in GUARDS.items()
        if guard.pattern(row["text"]) and not row[label]
    ]
    assert false_alarms == []

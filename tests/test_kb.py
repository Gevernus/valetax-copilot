"""The KB loads with stable ids, tagged conflicts, and the defect kept out of the prompt."""

from copilot import terms
from copilot.kb import load_kb


def test_kb_loads_with_stable_ids_and_version() -> None:
    kb = load_kb()
    assert len(kb.sections) == 20
    assert len(kb.version) == 12
    assert kb.version == load_kb().version


def test_duplicated_faq_is_stored_once_with_both_pages() -> None:
    section = load_kb().sections["funding.min-deposit"]
    assert section.urls == (
        "https://valetax.com/how-to-deposit/",
        "https://valetax.com/how-to-withdraw/",
    )


def test_conflicting_sections_are_marked() -> None:
    kb = load_kb()
    assert kb.has_conflict("funding.credit-time")
    assert kb.has_conflict("withdraw.steps")  # I7
    assert not kb.has_conflict("funding.min-deposit")  # a gap, not a conflict


def test_speed_words_sit_only_in_the_kbs_conflicts() -> None:
    # terms.CONTESTED: a speed claim is a conflict whatever it cites, because the KB says
    # "instant" or "immediately" only here (I1 on the deposit page, I5, I7). A new one is a review.
    kb = load_kb()
    speedy = {s.id for s in kb.sections.values() if "speed" in terms.policy_words(s.text)}
    assert speedy == {
        "deposit.steps",  # I1: the intro's "instant" funding methods
        "funding.credit-time",
        "funding.available-for-trading",
        "withdraw.steps",
        "open.sign-up",
    }
    assert all(kb.has_conflict(s) for s in speedy - {"deposit.steps"})


def test_defective_section_is_not_shown_to_the_drafter() -> None:
    kb = load_kb()
    assert "withdraw.steps" in kb.sections
    assert "withdraw.steps" not in {s.id for s in kb.citable}
    assert "fund withdrawals easy and instant" not in kb.prompt_block

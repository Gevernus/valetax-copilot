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
    assert kb.has_conflict("withdraw.steps")
    assert not kb.has_conflict("funding.min-deposit")  # a gap, not a conflict

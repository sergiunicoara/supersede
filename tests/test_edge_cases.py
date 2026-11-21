"""Edge cases found in the hackathon audit (see AUDIT.md, Part C), now with their fixes.

Writes are strict: a reference to something that does not exist, a reused fact id, a non-integer
authority, or a cycle in SUPERSEDES raises ValueError. Reads follow the whole chain and report
conflicts inside a single revision.
"""
import pytest

from supersede.store import Store


def _doc(s: Store, doc: str, authority, revs: int = 1) -> list[str]:
    s.add_document(doc, doc, authority)
    return [s.add_revision(doc, i, f"2025-01-{(i - 1) % 28 + 1:02d}") for i in range(1, revs + 1)]


# -- behavior that was already correct -------------------------------------------------------
def test_highest_authority_group_agreeing_wins_over_lower_dissent():
    s = Store()
    for doc, auth, value in (("A", 3, "x1"), ("B", 3, "x1"), ("C", 1, "x2")):
        (r,) = _doc(s, doc, auth)
        s.assert_fact(r, f"F{doc}", "k", "p", value)
    a = s.answer("k", "p")
    assert (a["status"], a["value"]) == ("resolved", "x1")


def test_revision_superseded_by_two_newer_ones_leaves_both_current():
    s = Store()
    r1, r2, r3 = _doc(s, "A", 3, revs=3)
    s.supersede(r2, r1)
    s.supersede(r3, r1)
    s.assert_fact(r2, "F2", "k", "p", "two")
    s.assert_fact(r3, "F3", "k", "p", "three")
    assert s.current_revisions() == ["A-r2", "A-r3"]
    assert s.answer("k", "p")["status"] == "unresolved"  # same document, same authority


def test_fact_not_restated_in_newer_revision_is_no_longer_current():
    """Design: a revision replaces the whole previous one; facts are not carried forward."""
    s = Store()
    r1, r2 = _doc(s, "A", 3, revs=2)
    s.assert_fact(r1, "F1", "k", "p", "one")
    s.supersede(r2, r1)
    assert s.answer("k", "p")["status"] == "unknown"


def test_values_are_compared_as_exact_strings():
    """Known limitation: '100%' and '100 %' count as a conflict (no normalisation)."""
    s = Store()
    (ra,) = _doc(s, "A", 3)
    (rb,) = _doc(s, "B", 1)
    s.assert_fact(ra, "F1", "k", "p", "100%")
    s.assert_fact(rb, "F2", "k", "p", "100 %")
    assert len(s.contradictions()) == 1


# -- defects found in the audit, now fixed ---------------------------------------------------
def test_history_lists_every_replaced_revision_in_a_long_chain():
    """Was capped at 20 hops."""
    s = Store()
    revs = _doc(s, "A", 3, revs=120)
    for newer, older in zip(revs[1:], revs[:-1]):
        s.supersede(newer, older)
    h = s.history("A-r120")
    assert len(h) == 119 and h[0] == "A-r119" and h[-1] == "A-r1"


def test_reused_fact_id_is_refused_and_leaves_the_first_fact_intact():
    """Was a silent overwrite that linked one fact node to two revisions."""
    s = Store()
    (ra,) = _doc(s, "A", 3)
    (rb,) = _doc(s, "B", 1)
    s.assert_fact(ra, "F1", "x", "p", "one")
    with pytest.raises(ValueError, match="already used"):
        s.assert_fact(rb, "F1", "y", "q", "two")
    assert s.answer("x", "p")["value"] == "one"
    assert s.answer("y", "q")["status"] == "unknown"


def test_reasserting_the_same_fact_id_in_the_same_revision_updates_it():
    s = Store()
    (r,) = _doc(s, "A", 3)
    s.assert_fact(r, "F1", "x", "p", "old")
    s.assert_fact(r, "F1", "x", "p", "new")
    assert s.answer("x", "p")["value"] == "new"


@pytest.mark.parametrize("bad", [None, "3", 2.5, True])
def test_authority_must_be_an_integer(bad):
    """Was a TypeError later, inside find_contradictions."""
    with pytest.raises(ValueError, match="authority"):
        Store().add_document("A", "a", bad)


def test_conflict_inside_one_revision_is_listed_by_contradictions():
    """Was invisible: the join could not bind the same HAS_REV edge twice."""
    s = Store()
    (r,) = _doc(s, "A", 3)
    s.assert_fact(r, "F1", "k", "p", "one")
    s.assert_fact(r, "F2", "k", "p", "two")
    assert s.answer("k", "p")["status"] == "unresolved"
    (c,) = s.contradictions()
    assert (c.left_doc, c.right_doc, c.winner) == ("A", "A", None)


def test_writes_that_reference_missing_things_raise():
    """Were silent no-ops."""
    s = Store()
    r1, r2 = _doc(s, "A", 3, revs=2)
    with pytest.raises(ValueError, match="unknown revision"):
        s.supersede("A-r9", "A-r1")
    with pytest.raises(ValueError, match="unknown revision"):
        s.supersede("A-r2", "A-r9")
    with pytest.raises(ValueError, match="unknown revision"):
        s.assert_fact("NOPE-r1", "F1", "x", "p", "v")
    with pytest.raises(ValueError, match="unknown document"):
        s.add_revision("NOPE", 1, "2025-01-01")
    assert s.current_revisions() == [r1, r2]  # nothing was written


def test_supersession_cycles_are_refused():
    """Was accepted: a cycle left no revision current and history() returned the revision itself."""
    s = Store()
    r1, r2, r3 = _doc(s, "A", 3, revs=3)
    s.supersede(r2, r1)
    s.supersede(r3, r2)
    with pytest.raises(ValueError, match="cycle"):
        s.supersede(r1, r2)  # direct cycle
    with pytest.raises(ValueError, match="cycle"):
        s.supersede(r1, r3)  # indirect cycle
    with pytest.raises(ValueError, match="cycle"):
        s.supersede(r1, r1)  # self-loop
    assert s.current_revisions() == [r3]
    assert s.history(r3) == [r2, r1]

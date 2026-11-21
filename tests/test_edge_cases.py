"""Edge cases found in the hackathon audit (see AUDIT.md, Part C).

Plain tests pin behavior that is correct today. Tests marked xfail(strict=True) describe a known
defect: they fail now (expected), and will turn into an unexpected pass, failing the suite, once
the defect is fixed, so the marker gets removed together with the fix.
"""
import pytest

from supersede.store import Store


def _doc(s: Store, doc: str, authority, revs: int = 1) -> list[str]:
    s.add_document(doc, doc, authority)
    return [s.add_revision(doc, i, f"2025-01-{i:02d}") for i in range(1, revs + 1)]


# -- correct today -------------------------------------------------------------------------
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


def test_supersession_cycle_leaves_nothing_current():
    s = Store()
    r1, r2 = _doc(s, "A", 3, revs=2)
    s.assert_fact(r2, "F2", "k", "p", "two")
    s.supersede(r2, r1)
    s.supersede(r1, r2)
    assert s.current_revisions() == []
    assert s.answer("k", "p")["status"] == "unknown"


# -- known defects ---------------------------------------------------------------------------
@pytest.mark.xfail(strict=True, reason="history() caps the SUPERSEDES traversal at 20 hops")
def test_history_lists_every_replaced_revision_in_a_long_chain():
    s = Store()
    revs = _doc(s, "A", 3, revs=25)
    for newer, older in zip(revs[1:], revs[:-1]):
        s.supersede(newer, older)
    assert len(s.history("A-r25")) == 24


@pytest.mark.xfail(strict=True, reason="assert_fact MERGEs on fid: a reused id rewrites the other revision's fact")
def test_reused_fact_id_does_not_rewrite_another_revisions_fact():
    s = Store()
    (ra,) = _doc(s, "A", 3)
    (rb,) = _doc(s, "B", 1)
    s.assert_fact(ra, "F1", "x", "p", "one")
    s.assert_fact(rb, "F1", "y", "q", "two")
    assert s.answer("x", "p")["value"] == "one"


@pytest.mark.xfail(strict=True, raises=TypeError, reason="a document without authority crashes the winner comparison")
def test_document_without_authority_does_not_crash():
    s = Store()
    (ra,) = _doc(s, "A", None)
    (rb,) = _doc(s, "B", 2)
    s.assert_fact(ra, "F1", "k", "p", "one")
    s.assert_fact(rb, "F2", "k", "p", "two")
    s.contradictions()[0].winner


@pytest.mark.xfail(strict=True, reason="the contradiction join cannot bind the same HAS_REV edge twice")
def test_conflict_inside_one_revision_is_listed_by_contradictions():
    s = Store()
    (r,) = _doc(s, "A", 3)
    s.assert_fact(r, "F1", "k", "p", "one")
    s.assert_fact(r, "F2", "k", "p", "two")
    assert s.answer("k", "p")["status"] == "unresolved"
    assert len(s.contradictions()) == 1


@pytest.mark.xfail(strict=True, reason="in a SUPERSEDES cycle history() returns the revision itself")
def test_history_never_contains_the_revision_itself():
    s = Store()
    r1, r2 = _doc(s, "A", 3, revs=2)
    s.supersede(r2, r1)
    s.supersede(r1, r2)
    assert r2 not in s.history(r2)


@pytest.mark.xfail(strict=True, reason="writes that reference a missing document or revision are silently ignored")
def test_superseding_a_missing_revision_raises():
    s = Store()
    _doc(s, "A", 3)
    with pytest.raises(Exception):
        s.supersede("A-r9", "A-r8")

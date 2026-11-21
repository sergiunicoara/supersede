import sys, pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from supersede.store import Store  # noqa: E402


def build() -> Store:
    s = Store()
    s.add_document("QP-07", "Final inspection procedure", authority=3)
    s.add_document("WI-12", "Shift work instruction", authority=1)
    r1 = s.add_revision("QP-07", 1, "2024-01-01")
    r2 = s.add_revision("QP-07", 2, "2025-03-01")
    w1 = s.add_revision("WI-12", 1, "2025-06-01")
    s.supersede(r2, r1)
    s.assert_fact(r1, "F1", "final_inspection", "sampling", "100%")
    s.assert_fact(r2, "F2", "final_inspection", "sampling", "AQL 1.0")
    s.assert_fact(w1, "F3", "final_inspection", "sampling", "100%")
    return s


def test_current_revisions_exclude_superseded():
    assert build().current_revisions() == ["QP-07-r2", "WI-12-r1"]


def test_history_lists_replaced_revisions():
    assert build().history("QP-07-r2") == ["QP-07-r1"]


def test_stale_fact_is_not_a_contradiction():
    # F1 (QP-07 rev1, superseded) disagrees with F2, but that is history, not a conflict.
    cs = build().contradictions()
    pairs = {(c.left_fact, c.right_fact) for c in cs}
    assert pairs == {("F2", "F3")}


def test_authority_resolves_contradiction():
    c = build().contradictions()[0]
    assert c.winner == "F2"


def test_answer_explains_why():
    a = build().answer("final_inspection", "sampling")
    assert a["status"] == "resolved"
    assert a["value"] == "AQL 1.0"
    assert a["source"] == "QP-07-r2"
    assert "outranks" in a["reason"]


def test_equal_authority_conflict_is_reported_not_hidden():
    s = Store()
    s.add_document("A", "a", authority=2)
    s.add_document("B", "b", authority=2)
    ra = s.add_revision("A", 1, "2025-01-01")
    rb = s.add_revision("B", 1, "2025-01-01")
    s.assert_fact(ra, "X1", "k", "p", "one")
    s.assert_fact(rb, "X2", "k", "p", "two")
    assert s.answer("k", "p")["status"] == "unresolved"
    assert s.contradictions()[0].winner is None


def test_unknown_when_nothing_asserted():
    assert Store().answer("nope", "nope")["status"] == "unknown"


def test_persists_across_reopen(tmp_path):
    p = str(tmp_path / "kb.relate")
    s = Store(p)
    s.add_document("D", "d", authority=1)
    s.commit()
    s.close()
    s2 = Store(p)
    assert s2._run("MATCH (d:Doc) RETURN count(d) AS n")[0]["n"] == 1


def test_usable_from_other_threads():
    """Regression: Relate connections are thread-affine; an MCP server calls from worker threads."""
    import threading

    s = build()
    out: dict = {}

    def work():
        out["answer"] = s.answer("final_inspection", "sampling")["value"]
        out["hist"] = s.history("QP-07-r2")

    t = threading.Thread(target=work)
    t.start()
    t.join()
    assert out == {"answer": "AQL 1.0", "hist": ["QP-07-r1"]}

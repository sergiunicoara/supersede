import pathlib
import re
import sys

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
for sub in ("src", "examples", "eval"):
    sys.path.insert(0, str(ROOT / sub))

import baseline  # noqa: E402
import run_eval  # noqa: E402
from load_corpus import CORPUS_DIR, counts, load_docs, read_corpus  # noqa: E402
from supersede.store import Store  # noqa: E402

CASES_MD = CORPUS_DIR / "CASES.md"
QUESTIONS = yaml.safe_load((ROOT / "eval" / "questions.yaml").read_text(encoding="utf-8"))["questions"]


def loaded() -> Store:
    s = Store()
    load_docs(s, read_corpus())
    return s


def test_corpus_loads():
    docs = read_corpus()
    d, r, f = counts(docs)
    assert (d, r, f) == (12, 19, 34)
    assert {doc["authority"] for doc in docs} == {1, 2, 3, 4}
    assert any(len(doc["revisions"]) == 3 for doc in docs)
    s = loaded()
    # every document has exactly one revision not superseded
    assert len(s.current_revisions()) == len(docs)
    assert s._run("MATCH (f:Fact) RETURN count(f) AS n")[0]["n"] == f


def test_every_case_in_cases_md_has_a_question():
    cases = set(re.findall(r"^## Case `(\w+)`", CASES_MD.read_text(encoding="utf-8"), re.M))
    assert cases == {"stale", "authority", "unresolved", "agreed", "unknown", "chain"}
    used = {q["case"] for q in QUESTIONS}
    assert cases <= used, f"cases without a question: {cases - used}"
    assert used <= cases, f"questions with an undocumented case: {used - cases}"


def test_eval_passes():
    rows = run_eval.evaluate()
    assert len(rows) == len(QUESTIONS) >= 10
    failed = [x["q"]["id"] for x in rows if not x["ok"]]
    assert not failed, f"Supersede failed: {failed}"


def test_only_current_revisions_conflict():
    """The corpus' stale facts disagree with current ones but must not be reported."""
    s = loaded()
    keys = {(c.subject, c.predicate) for c in s.contradictions()}
    assert keys == {
        ("final_inspection", "sampling"),
        ("retained_sample", "retention_period"),
        ("paint_line", "film_thickness_um"),
        ("machining_cell", "tool_change_interval"),
        ("line_3", "changeover_target_min"),
    }
    stale_ids = {
        f["id"]
        for d in read_corpus()
        for r in d["revisions"]
        if f"{d['id']}-r{r['rev']}" not in set(s.current_revisions())
        for f in r["facts"]
    }
    assert stale_ids
    for c in s.contradictions():
        assert c.left_fact not in stale_ids and c.right_fact not in stale_ids


def test_three_revision_history():
    assert loaded().history("QP-07-r3") == ["QP-07-r2", "QP-07-r1"]


def test_baseline_is_newest_date_only():
    docs = read_corpus()
    # the shift note is the newest source for this fact; the baseline takes it regardless of authority
    assert baseline.answer(docs, "retained_sample", "retention_period")["source"] == "SN-0914-r1"
    assert baseline.answer(docs, "nothing", "nothing") == {"status": "unknown"}


def test_seed_demo_still_works(tmp_path):
    from seed_demo import seed

    p = str(tmp_path / "demo.relate")
    seed(p)
    s = Store(p)
    assert s.answer("final_inspection", "sampling")["value"] == "AQL 0.65"

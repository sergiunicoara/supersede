import asyncio
import json
import pathlib
import shutil
import sys

import pytest
from mcp.client import Client
from mcp.client.stdio import StdioServerParameters, stdio_client

from supersede.store import Store

ROOT = pathlib.Path(__file__).resolve().parents[1]
for sub in ("examples", "eval"):
    sys.path.insert(0, str(ROOT / sub))

import run_eval  # noqa: E402
from load_corpus import load_docs, read_corpus, read_topics  # noqa: E402

STORE = ROOT / "examples" / "store" / "supersede-demo.relate"


def corpus() -> Store:
    s = Store()
    load_docs(s, read_corpus(), read_topics())
    return s


def two_revisions(eff1="2025-01-01", eff2="2025-02-01") -> Store:
    s = Store()
    s.add_document("A", "a", 3)
    r1, r2 = s.add_revision("A", 1, eff1), s.add_revision("A", 2, eff2)
    s.supersede(r2, r1)
    s.assert_fact(r1, "F1", "k", "p", "old")
    s.assert_fact(r2, "F2", "k", "p", "new")
    return s


# -- ask: retrieval feeds graph reasoning ---------------------------------------------------------
def test_ask_finds_the_topic_and_lets_the_graph_decide():
    r = corpus().ask("How long do we have to keep retained samples?")
    assert r["status"] == "resolved"
    assert (r["matched"]["subject"], r["matched"]["predicate"]) == ("retained_sample", "retention_period")
    assert (r["answer"]["value"], r["answer"]["source"]) == ("10 years", "CSR-VEL-01-r2")
    assert {o["value"] for o in r["answer"]["overruled"]} == {"5 years", "3 years"}  # authority, not the newest date


def test_ask_says_no_match_instead_of_guessing():
    s = corpus()
    assert s.ask("What colour are the delivery trucks?")["status"] == "no_match"
    assert s.ask("Is it the or a?")["status"] == "no_match"  # nothing searchable once stop words are dropped
    assert s.ask("")["status"] == "no_match"


def test_ask_survives_search_syntax_in_the_question():
    r = corpus().ask('retained samples?? AND (kept) "x" * : OR NOT -')
    assert r["status"] in {"resolved", "agreed", "unresolved", "unknown", "no_match"}


def test_ask_reports_alternatives_and_honours_k():
    s = corpus()
    assert len(s.ask("how long are records kept", k=3).get("alternatives", [])) <= 2
    assert s.ask("how long are records kept", k=1)["alternatives"] == []


def test_ask_warns_when_the_answer_rests_on_a_stale_source():
    r = corpus().ask("Which form do inspectors fill in for final inspection results?")
    assert r["answer"]["value"] == "FORM-9"
    assert [x["revision"] for x in r["stale_sources"]] == ["WI-52-r1"]  # written from a superseded revision


def test_ask_without_topics_explains_what_is_missing():
    s = two_revisions()
    r = s.ask("what is new")
    assert r["status"] == "no_topics" and "add_topic" in r["reason"]


def test_add_topic_needs_a_description():
    with pytest.raises(ValueError, match="description"):
        Store().add_topic("k", "p", "   ")


def test_search_index_persists_in_the_committed_store_opened_read_only(tmp_path):
    db = tmp_path / "copy.relate"
    shutil.copytree(STORE, db)
    s = Store(str(db), read_only=True)
    try:
        r = s.ask("For how long do we have to store the reference samples?")
        assert r["answer"]["value"] == "10 years"
    finally:
        s.close()


# -- time ------------------------------------------------------------------------------------------
def test_in_force_boundaries_are_inclusive_on_the_effective_day():
    s = two_revisions()
    assert s.in_force("2024-12-31") == set()
    assert s.in_force("2025-01-01") == {"A-r1"}
    assert s.in_force("2025-01-31") == {"A-r1"}
    assert s.in_force("2025-02-01") == {"A-r2"}  # the successor takes over on its own effective day


def test_answer_as_of_follows_the_dates():
    s = two_revisions()
    assert s.answer("k", "p", as_of="2025-01-15")["value"] == "old"
    assert s.answer("k", "p", as_of="2025-03-01")["value"] == "new"
    assert s.answer("k", "p", as_of="2024-01-01")["status"] == "unknown"
    assert s.answer("k", "p")["value"] == "new"  # no date: unchanged behaviour


@pytest.mark.parametrize("bad", ["2025/01/01", "yesterday", "", "2025-13-40"])
def test_as_of_must_be_a_real_date(bad):
    with pytest.raises(ValueError, match="as_of"):
        two_revisions().answer("k", "p", as_of=bad)


def test_an_undated_revision_cannot_end_its_predecessor_and_is_reported():
    s = two_revisions(eff2="")
    assert s.in_force("2030-01-01") == {"A-r1"}
    got = s.answer("k", "p", as_of="2030-01-01")
    assert got["value"] == "old"
    assert [(w["revision"], w["issue"]) for w in got["warnings"]] == [("A-r2", "missing_date")]


def test_date_warnings_find_the_corpus_problems_and_nothing_else():
    got = {(w["revision"], w["issue"]) for w in corpus().date_warnings()}
    assert got == {("QP-22-r1", "future_date"), ("QP-22-r2", "dated_before_predecessor"),
                   ("WI-31-r2", "missing_date")}


def test_unreadable_dates_are_reported_not_guessed():
    s = two_revisions(eff1="2025/01/01")
    assert [(w["revision"], w["issue"]) for w in s.date_warnings()] == [("A-r1", "invalid_date")]


# -- the evaluation sections -----------------------------------------------------------------------
def test_as_of_eval_passes():
    rows = run_eval.evaluate_as_of()
    assert len(rows) == 13 and all(x["ok"] for x in rows), [x["q"]["id"] for x in rows if not x["ok"]]


def test_retrieval_eval_beats_the_naive_baselines():
    rows = run_eval.evaluate_retrieval()
    n = len(rows)
    assert n == 23
    assert sum(x["key_ok"] for x in rows) > sum(x["naive_key_ok"] for x in rows)
    assert sum(x["ok"] for x in rows) > sum(x["same_retrieval_newest_ok"] for x in rows)  # the graph adds value
    assert sum(x["ok"] for x in rows) == n


# -- over MCP --------------------------------------------------------------------------------------
def _call(db, tool, args):
    async def run():
        params = StdioServerParameters(command=sys.executable, args=["-m", "supersede.mcp_server", "--db", str(db)],
                                       env={"PYTHONPATH": str(ROOT / "src")})
        async with Client(stdio_client(params, errlog=open(pathlib.Path(db).parent / "e.log", "w"))) as c:
            r = await c.call_tool(tool, args)
            return r.structured_content["result"] if r.structured_content and "result" in r.structured_content \
                else (r.structured_content or json.loads(r.content[0].text))

    return asyncio.run(run())


def test_the_new_tools_work_over_mcp(tmp_path):
    db = tmp_path / "copy.relate"
    shutil.copytree(STORE, db)
    a = _call(db, "ask", {"question": "What torque do we use on the cylinder head bolts?", "as_of": "2025-10-01"})
    assert a["answer"]["value"] == "48 Nm" and a["answer"]["as_of"] == "2025-10-01"
    b = _call(db, "answer_as_of", {"subject": "final_inspection", "predicate": "sampling", "date": "2025-07-01"})
    assert (b["status"], b["value"], b["source"]) == ("resolved", "AQL 1.0", "QP-07-r2")
    w = _call(db, "date_warnings", {})
    assert {x["issue"] for x in w} == {"future_date", "dated_before_predecessor", "missing_date"}

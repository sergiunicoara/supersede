import pathlib
import subprocess
import sys

import pytest

from supersede.ingest import ingest_directory, parse
from supersede.store import Store

ROOT = pathlib.Path(__file__).resolve().parents[1]
DOCS = ROOT / "examples" / "documents"

HEADER = "---\ndoc: D1\ntitle: Test doc\nauthority: 3\nrevision: 1\neffective: 2025-01-01\n---\n"


def test_parse_reads_header_and_inline_facts():
    r = parse(HEADER + "Pack {{packaging.units_per_box = 24}} per box, label {{packaging.label = A = B}}.")
    assert (r.doc, r.title, r.authority, r.rev, r.effective, r.supersedes) == ("D1", "Test doc", 3, 1, "2025-01-01", None)
    assert r.facts == (("packaging", "units_per_box", "24"), ("packaging", "label", "A = B"))


def test_parse_accepts_crlf_comments_and_supersedes():
    text = HEADER.replace("---\n", "---\r\n").replace("revision: 1", "revision: 2  # new\r\nsupersedes: 1")
    r = parse(text + "{{k.p = v}}")
    assert (r.rev, r.supersedes, r.facts) == (2, 1, (("k", "p", "v"),))


@pytest.mark.parametrize("text, message", [
    ("no header\n{{a.b = c}}", "must start with"),
    ("---\ndoc: D1\n", "not closed"),
    (HEADER.replace("authority: 3\n", ""), "missing header field"),
    (HEADER.replace("authority: 3", "authority: high"), "must be integers"),
    ("---\ndoc D1\n---\n", "bad header line"),
])
def test_parse_rejects_bad_documents(text, message):
    with pytest.raises(ValueError, match=message):
        parse(text, "bad.md")


def test_derived_from_header_is_parsed_and_validated(tmp_path):
    r = parse(HEADER.replace("revision: 1", "revision: 1\nderived_from: X-r1, Y-r2") + "{{k.p = v}}")
    assert r.derived_from == ("X-r1", "Y-r2")
    (tmp_path / "a.md").write_text(HEADER.replace("revision: 1", "revision: 1\nderived_from: NOPE-r1"), encoding="utf-8")
    with pytest.raises(ValueError, match="derived_from"):
        ingest_directory(Store(), tmp_path)


def test_unannotated_prose_yields_no_facts():
    assert parse(HEADER + "Pack 24 to a box. The label language is English.").facts == ()


def test_example_documents_ingest_and_answer_like_the_corpus_semantics():
    s = Store()
    assert ingest_directory(s, DOCS) == (3, 4, 8)
    # revision 2 replaces revision 1, so the old value 12 is history, not a conflict
    assert s.current_revisions() == ["CSR-ORL-01-r1", "QP-40-r2", "WI-41-r1"]
    a = s.answer("packaging", "units_per_box")
    assert (a["status"], a["value"], a["source"]) == ("resolved", "24", "QP-40-r2")
    assert s.answer("packaging", "label_language")["status"] == "agreed"
    assert s.history("QP-40-r2") == ["QP-40-r1"]
    assert [(c.subject, c.predicate) for c in s.contradictions()] == [("packaging", "units_per_box")]
    # WI-41 r1 was written from QP-40 r1, which QP-40 r2 replaced
    assert s.stale_derivations() == [
        {"revision": "WI-41-r1", "source": "QP-40-r1", "hops": 1, "replaced_by": ["QP-40-r2"]}]


def test_inconsistent_authority_for_one_document_is_refused(tmp_path):
    (tmp_path / "a.md").write_text(HEADER, encoding="utf-8")
    (tmp_path / "b.md").write_text(HEADER.replace("revision: 1", "revision: 2").replace("authority: 3", "authority: 1"), encoding="utf-8")
    with pytest.raises(ValueError, match="authority"):
        ingest_directory(Store(), tmp_path)


def test_missing_superseded_revision_and_duplicates_are_refused(tmp_path):
    (tmp_path / "a.md").write_text(HEADER.replace("revision: 1", "revision: 2\nsupersedes: 1"), encoding="utf-8")
    with pytest.raises(ValueError, match="not found"):
        ingest_directory(Store(), tmp_path)
    (tmp_path / "a.md").write_text(HEADER, encoding="utf-8")
    (tmp_path / "b.md").write_text(HEADER, encoding="utf-8")
    with pytest.raises(ValueError, match="twice"):
        ingest_directory(Store(), tmp_path)


def test_empty_directory_is_refused(tmp_path):
    with pytest.raises(ValueError, match="no \\*.md"):
        ingest_directory(Store(), tmp_path)


def test_cli_builds_a_store_and_refuses_an_existing_path(tmp_path):
    db = tmp_path / "ingested.relate"
    cmd = [sys.executable, "-m", "supersede.ingest", str(DOCS), "--db", str(db)]
    env = {"PYTHONPATH": str(ROOT / "src"), "SYSTEMROOT": __import__("os").environ.get("SYSTEMROOT", "")}
    ok = subprocess.run(cmd, capture_output=True, text=True, timeout=60, env=env)
    assert ok.returncode == 0 and "3 documents, 4 revisions, 8 facts" in ok.stdout, ok.stderr
    again = subprocess.run(cmd, capture_output=True, text=True, timeout=60, env=env)
    assert again.returncode != 0 and "already exists" in again.stderr
    s = Store(str(db), read_only=True)
    assert s.answer("packaging", "units_per_box")["value"] == "24"
    s.close()

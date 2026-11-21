"""The committed demo store (examples/store/supersede-demo.relate) must open and match the corpus."""
import pathlib
import shutil
import sys

import relate

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "examples"))
from load_corpus import counts, read_corpus  # noqa: E402

from supersede.store import Store  # noqa: E402

STORE = ROOT / "examples" / "store" / "supersede-demo.relate"


def _copy(tmp_path) -> str:
    dst = tmp_path / "store.relate"
    shutil.copytree(STORE, dst)  # never open the committed files themselves
    return str(dst)


def test_committed_store_opens_read_only_and_matches_corpus(tmp_path):
    docs, revs, facts = counts(read_corpus())
    conn = relate.connect(_copy(tmp_path), read_only=True)
    cur = conn.cursor()
    got = {}
    for label in ("Doc", "Rev", "Fact"):
        cur.execute(f"MATCH (n:{label}) RETURN count(n) AS n")
        got[label] = cur.fetchall()[0]["n"]
    conn.close()
    assert got == {"Doc": docs, "Rev": revs, "Fact": facts}


def test_committed_store_answers_like_the_corpus(tmp_path):
    s = Store(_copy(tmp_path))
    try:
        a = s.answer("retained_sample", "retention_period")
        assert (a["status"], a["value"], a["source"]) == ("resolved", "10 years", "CSR-VEL-01-r2")
        assert s.history("QP-07-r3") == ["QP-07-r2", "QP-07-r1"]
    finally:
        s.close()

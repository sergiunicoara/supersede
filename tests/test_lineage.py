import asyncio
import pathlib
import shutil
import sys

import pytest
from mcp.client import Client
from mcp.client.stdio import StdioServerParameters, stdio_client

from supersede.store import Store

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _two_docs() -> Store:
    s = Store()
    s.add_document("A", "a", 3)
    s.add_document("B", "b", 2)
    return s


def test_derive_validates_its_arguments():
    s = _two_docs()
    a1 = s.add_revision("A", 1, "2025-01-01")
    a2 = s.add_revision("A", 2, "2025-02-01")
    b1 = s.add_revision("B", 1, "2025-03-01")
    with pytest.raises(ValueError, match="unknown revision"):
        s.derive(b1, "A-r9")
    with pytest.raises(ValueError, match="unknown revision"):
        s.derive("B-r9", a1)
    with pytest.raises(ValueError, match="same document"):
        s.derive(a2, a1)  # that is what supersede() is for
    s.derive(b1, a1)
    assert s.lineage(b1)[0]["source"] == a1


def test_derive_refuses_cycles():
    s = _two_docs()
    a1 = s.add_revision("A", 1, "2025-01-01")
    b1 = s.add_revision("B", 1, "2025-01-01")
    s.add_document("C", "c", 1)
    c1 = s.add_revision("C", 1, "2025-01-01")
    s.derive(b1, a1)
    s.derive(c1, b1)
    with pytest.raises(ValueError, match="cycle"):
        s.derive(a1, b1)  # direct
    with pytest.raises(ValueError, match="cycle"):
        s.derive(a1, c1)  # indirect


def test_stale_derivation_needs_a_current_derived_revision_and_a_superseded_source():
    s = _two_docs()
    a1, a2 = s.add_revision("A", 1, "2025-01-01"), s.add_revision("A", 2, "2025-02-01")
    b1, b2 = s.add_revision("B", 1, "2025-03-01"), s.add_revision("B", 2, "2025-04-01")
    s.supersede(a2, a1)
    s.derive(b1, a1)
    assert [x["revision"] for x in s.stale_derivations()] == ["B-r1"]
    s.supersede(b2, b1)  # the derived revision is itself replaced: no longer current, no longer reported
    assert s.stale_derivations() == []
    s.derive(b2, a2)  # the new revision is built on the current source: fine
    assert s.stale_derivations() == []


def test_chain_reports_the_superseded_source_and_hops_with_a_long_replacement_chain():
    s = Store()
    for d in "ABC":
        s.add_document(d, d, 1)
    a = [s.add_revision("A", i, f"2025-01-{i:02d}") for i in range(1, 6)]
    for newer, older in zip(a[1:], a[:-1]):
        s.supersede(newer, older)
    b1, c1 = s.add_revision("B", 1, "2025-02-01"), s.add_revision("C", 1, "2025-03-01")
    s.derive(b1, a[0])
    s.derive(c1, b1)
    assert s.stale_derivations() == [
        {"revision": "B-r1", "source": "A-r1", "hops": 1, "replaced_by": ["A-r5"]},
        {"revision": "C-r1", "source": "A-r1", "hops": 2, "replaced_by": ["A-r5"]},
    ]
    assert [x["source"] for x in s.lineage(c1)] == ["B-r1", "A-r1"]


def test_stale_derivations_over_mcp_on_the_committed_store(tmp_path):
    db = tmp_path / "copy.relate"
    shutil.copytree(ROOT / "examples" / "store" / "supersede-demo.relate", db)

    async def run():
        params = StdioServerParameters(command=sys.executable, args=["-m", "supersede.mcp_server", "--db", str(db)],
                                       env={"PYTHONPATH": str(ROOT / "src")})
        async with Client(stdio_client(params, errlog=open(tmp_path / "e.log", "w"))) as c:
            tools = [t.name for t in (await c.list_tools()).tools]
            r = await c.call_tool("stale_derivations", {})
            return tools, r.structured_content["result"]

    tools, rows = asyncio.run(run())
    assert tools == ["current_answer", "find_contradictions", "current_revisions", "revision_history",
                     "stale_derivations"]
    assert [(x["revision"], x["source"], x["hops"]) for x in rows] == [
        ("SN-0914-r1", "CSR-VEL-01-r1", 1), ("WI-12-r1", "QP-07-r1", 1), ("WI-52-r1", "QP-07-r1", 2)]

import asyncio
import pathlib
import sys

from mcp.client import Client
from mcp.client.stdio import StdioServerParameters, stdio_client

from supersede.store import Store

ROOT = pathlib.Path(__file__).resolve().parents[1]


def test_server_exits_without_native_panic(tmp_path):
    """Regression: the server used to leave its Store open, and Relate panicked at exit."""
    db = str(tmp_path / "kb.relate")
    s = Store(db)
    s.add_document("D", "d", authority=1)
    s.commit()
    s.close()

    log_path = tmp_path / "server.log"

    async def run() -> list[str]:
        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "supersede.mcp_server", "--db", db],
            env={"PYTHONPATH": str(ROOT / "src")},
        )
        with open(log_path, "w", encoding="utf-8") as log:
            async with Client(stdio_client(params, errlog=log)) as c:
                return (await c.call_tool("current_revisions", {})).structured_content["result"]

    assert asyncio.run(run()) == []
    stderr = log_path.read_text(encoding="utf-8", errors="replace")
    assert "panicked" not in stderr and "Traceback" not in stderr, stderr


def test_server_refuses_a_missing_store_and_creates_nothing(tmp_path):
    import subprocess

    missing = tmp_path / "nope.relate"
    r = subprocess.run(
        [sys.executable, "-m", "supersede.mcp_server", "--db", str(missing)],
        capture_output=True, text=True, timeout=60, env={**__import__("os").environ, "PYTHONPATH": str(ROOT / "src")},
    )
    assert r.returncode != 0
    assert "store not found" in r.stderr
    assert not missing.exists()


def test_server_leaves_an_existing_store_byte_identical(tmp_path):
    import hashlib
    import shutil

    store = ROOT / "examples" / "store" / "supersede-demo.relate"
    db = tmp_path / "copy.relate"
    shutil.copytree(store, db)

    def digest() -> str:
        h = hashlib.sha256()
        for p in sorted(db.rglob("*")):
            if p.is_file():
                h.update(str(p.relative_to(db)).encode())
                h.update(p.read_bytes())
        return h.hexdigest()

    before = digest()

    async def run() -> str:
        params = StdioServerParameters(
            command=sys.executable, args=["-m", "supersede.mcp_server", "--db", str(db)],
            env={"PYTHONPATH": str(ROOT / "src")},
        )
        async with Client(stdio_client(params, errlog=open(tmp_path / "e.log", "w"))) as c:
            r = await c.call_tool("current_answer", {"subject": "retained_sample", "predicate": "retention_period"})
            return r.content[0].text

    assert "10 years" in asyncio.run(run())
    assert digest() == before  # read-only: no checkpoint, no WAL change

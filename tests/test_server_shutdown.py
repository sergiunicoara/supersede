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

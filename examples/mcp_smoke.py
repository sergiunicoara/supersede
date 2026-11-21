"""End-to-end check: spawn the MCP server over stdio and call its tools like an agent would."""
import asyncio, sys
from mcp.client import Client
from mcp.client.stdio import StdioServerParameters

async def main(db: str) -> None:
    params = StdioServerParameters(command=sys.executable,
                                   args=["-m", "supersede.mcp_server", "--db", db],
                                   env={"PYTHONPATH": "src"})
    async with Client(params) as c:
        tools = await c.list_tools()
        print("tools:", [t.name for t in tools.tools])
        r = await c.call_tool("current_answer", {"subject": "final_inspection", "predicate": "sampling"})
        print("current_answer ->", r.content[0].text[:300])
        r = await c.call_tool("revision_history", {"rev_id": "QP-07-r3"})
        print("revision_history ->", r.content[0].text)

asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "demo.relate"))

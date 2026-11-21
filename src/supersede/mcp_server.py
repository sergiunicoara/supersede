"""MCP server exposing Supersede's domain tools to any MCP-capable agent.

Agents get questions-with-reasons, not raw Cypher: which revision is in force,
which facts conflict, and who wins and why.

Run:  python -m supersede.mcp_server --db kb.relate
"""
from __future__ import annotations

import argparse
from dataclasses import asdict

from mcp.server.mcpserver import MCPServer

from .store import Store

server = MCPServer(
    name="supersede",
    instructions=(
        "Query a revision-aware knowledge graph. Use current_answer for 'what is in force', "
        "find_contradictions to audit conflicts between current revisions, and "
        "revision_history to see what a revision replaced. Superseded facts are history, "
        "never conflicts."
    ),
)
_store: Store | None = None


def _s() -> Store:
    assert _store is not None, "store not initialised"
    return _store


@server.tool()
def current_answer(subject: str, predicate: str) -> dict:
    """Which value is in force for (subject, predicate), with the reason and overruled sources."""
    return _s().answer(subject, predicate)


@server.tool()
def find_contradictions() -> list[dict]:
    """All conflicts between facts in current revisions, with the authority-based winner (or null on a tie)."""
    return [{**asdict(c), "winner": c.winner} for c in _s().contradictions()]


@server.tool()
def current_revisions() -> list[str]:
    """Revision ids that have not been superseded."""
    return _s().current_revisions()


@server.tool()
def revision_history(rev_id: str) -> list[str]:
    """Revisions that `rev_id` replaced, nearest first."""
    return _s().history(rev_id)


def main() -> None:
    global _store
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=":memory:", help="Relate database path (default: in-memory)")
    args = ap.parse_args()
    _store = Store(args.db)
    server.run("stdio")


if __name__ == "__main__":
    main()

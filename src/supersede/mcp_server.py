"""MCP server exposing Supersede's domain tools to any MCP-capable agent.

Agents get questions-with-reasons, not raw Cypher: which revision is in force,
which facts conflict, and who wins and why.

Run:  python -m supersede.mcp_server --db kb.relate
"""
from __future__ import annotations

import argparse
import os
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
    ap = argparse.ArgumentParser(
        description="Supersede MCP server (stdio). Every tool only reads, so an existing store is "
                    "opened read-only; the path must exist (build one with examples/load_corpus.py).")
    ap.add_argument("--db", default=":memory:",
                    help="path of an existing Relate store (default: an empty in-memory store)")
    args = ap.parse_args()
    in_memory = args.db == ":memory:"
    if not in_memory and not os.path.exists(args.db):
        # Without this check an MCP host that starts the server from another directory would
        # silently get a new, empty store.
        ap.error(f"store not found: {args.db} (use an absolute path; create one with "
                 f"examples/load_corpus.py or examples/seed_demo.py)")
    _store = Store(args.db, read_only=not in_memory)
    try:
        server.run("stdio")
    finally:
        # Close on the store's own thread; otherwise the connection is finalised during
        # interpreter shutdown and Relate's native layer panics.
        _store.close()


if __name__ == "__main__":
    main()

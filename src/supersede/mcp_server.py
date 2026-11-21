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
        "Query a revision-aware knowledge graph. Start with ask for a plain-language question: it "
        "finds the right topic by search and answers it from the graph, with the reason, what it "
        "overruled and any stale source. Use current_answer when you already know the subject and "
        "predicate, answer_as_of for 'what was in force on this date', date_warnings to see unreliable "
        "effective dates, find_contradictions to audit conflicts between current revisions, "
        "revision_history to see what a revision replaced, and stale_derivations to find current "
        "revisions that were written from a source that has since been superseded. Superseded "
        "facts are history, never conflicts."
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
def ask(question: str, as_of: str | None = None) -> dict:
    """Answer a plain-language question, e.g. 'how long must retained samples be kept?'.

    Search finds the matching topic; the graph decides the value in force (supersession, authority,
    ties), names the reason and the overruled sources, and warns if the revisions it rests on were
    written from a source that has since been superseded. Optional as_of is a date YYYY-MM-DD.
    status is no_match when no topic fits the question.
    """
    return _s().ask(question, as_of=as_of)


@server.tool()
def answer_as_of(subject: str, predicate: str, date: str) -> dict:
    """Which value was in force for (subject, predicate) on a date (YYYY-MM-DD), with warnings about
    missing, wrong or inconsistent effective dates that could affect the answer."""
    return _s().answer(subject, predicate, as_of=date)


@server.tool()
def date_warnings() -> list[dict]:
    """Effective-date problems in the store: missing or unreadable dates, dates in the future, and
    revisions dated before the revision they replace."""
    return _s().date_warnings()


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


@server.tool()
def stale_derivations() -> list[dict]:
    """Current revisions written from a source revision that has since been superseded, with the
    source, how many derivation hops away it is, and the revision(s) that replaced it."""
    return _s().stale_derivations()


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

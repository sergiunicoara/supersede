"""Supersede: an embedded knowledge store that knows which fact is currently in force.

Built on Relate (embedded graph DB, Cypher, in-process). Core idea: documents have
revisions linked by SUPERSEDES; facts belong to revisions; a contradiction only
counts between facts in *current* (not superseded) revisions, and is resolved by the
authority level of the owning document.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any

import relate


@dataclass(frozen=True)
class Contradiction:
    subject: str
    predicate: str
    left_fact: str
    left_value: str
    left_doc: str
    left_authority: int
    right_fact: str
    right_value: str
    right_doc: str
    right_authority: int

    @property
    def winner(self) -> str | None:
        """Fact id of the higher-authority side, or None if authority ties."""
        if self.left_authority == self.right_authority:
            return None
        return self.left_fact if self.left_authority > self.right_authority else self.right_fact


class Store:
    """All database work runs on ONE dedicated thread.

    Relate connections are thread-affine (DB-API threadsafety = 1), and an MCP server
    dispatches tool calls on worker threads. Funnelling every call through a single-thread
    executor keeps one connection valid for both file and in-memory databases.
    """

    def __init__(self, path: str = ":memory:") -> None:
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="relate")
        self._conn = self._pool.submit(relate.connect, path).result()

    # -- plumbing ---------------------------------------------------------
    def _run_sync(self, query: str, params: dict[str, Any] | None) -> list[dict[str, Any]]:
        cur = self._conn.cursor()
        if params is None:
            cur.execute(query)
        else:
            cur.execute(query, params)
        try:
            return cur.fetchall()
        except Exception:  # write statements return no rows
            return []

    def _run(self, query: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        return self._pool.submit(self._run_sync, query, params).result()

    def commit(self) -> None:
        self._pool.submit(self._conn.commit).result()

    def close(self) -> None:
        self._pool.submit(self._conn.close).result()
        self._pool.shutdown(wait=True)

    # -- writes -----------------------------------------------------------
    def add_document(self, doc_id: str, title: str, authority: int) -> None:
        self._run(
            "MERGE (d:Doc {id: $id}) SET d.title = $title, d.authority = $authority",
            {"id": doc_id, "title": title, "authority": authority},
        )

    def add_revision(self, doc_id: str, rev: int, effective: str) -> str:
        rev_id = f"{doc_id}-r{rev}"
        self._run(
            "MATCH (d:Doc {id: $doc}) "
            "MERGE (r:Rev {id: $rid}) SET r.doc = $doc, r.rev = $rev, r.effective = $eff "
            "MERGE (d)-[:HAS_REV]->(r)",
            {"doc": doc_id, "rid": rev_id, "rev": rev, "eff": effective},
        )
        return rev_id

    def supersede(self, newer_rev: str, older_rev: str) -> None:
        self._run(
            "MATCH (a:Rev {id: $n}), (b:Rev {id: $o}) MERGE (a)-[:SUPERSEDES]->(b)",
            {"n": newer_rev, "o": older_rev},
        )

    def assert_fact(self, rev_id: str, fact_id: str, subject: str, predicate: str, value: str) -> None:
        self._run(
            "MATCH (r:Rev {id: $r}) "
            "MERGE (f:Fact {fid: $f}) SET f.subject = $s, f.predicate = $p, f.value = $v "
            "MERGE (r)-[:ASSERTS]->(f)",
            {"r": rev_id, "f": fact_id, "s": subject, "p": predicate, "v": value},
        )

    # -- reads ------------------------------------------------------------
    def current_revisions(self) -> list[str]:
        rows = self._run(
            "MATCH (r:Rev) WHERE NOT (:Rev)-[:SUPERSEDES]->(r) RETURN r.id AS id ORDER BY id"
        )
        return [r["id"] for r in rows]

    def history(self, rev_id: str) -> list[str]:
        """Revisions that `rev_id` replaced, nearest first."""
        rows = self._run(
            "MATCH p=(n:Rev {id: $id})-[:SUPERSEDES*1..20]->(o:Rev) "
            "RETURN o.id AS id, length(p) AS hops ORDER BY hops",
            {"id": rev_id},
        )
        return [r["id"] for r in rows]

    def current_facts(self, subject: str, predicate: str) -> list[dict[str, Any]]:
        return self._run(
            "MATCH (d:Doc)-[:HAS_REV]->(r:Rev)-[:ASSERTS]->(f:Fact) "
            "WHERE f.subject = $s AND f.predicate = $p AND NOT (:Rev)-[:SUPERSEDES]->(r) "
            "RETURN f.fid AS fact, f.value AS value, r.id AS rev, d.id AS doc, d.authority AS authority "
            "ORDER BY authority DESC, fact",
            {"s": subject, "p": predicate},
        )

    def contradictions(self) -> list[Contradiction]:
        rows = self._run(
            """
            MATCH (da:Doc)-[:HAS_REV]->(ra:Rev)-[:ASSERTS]->(a:Fact),
                  (db:Doc)-[:HAS_REV]->(rb:Rev)-[:ASSERTS]->(b:Fact)
            WHERE a.subject = b.subject AND a.predicate = b.predicate
              AND a.value <> b.value AND a.fid < b.fid
              AND NOT (:Rev)-[:SUPERSEDES]->(ra) AND NOT (:Rev)-[:SUPERSEDES]->(rb)
            RETURN a.subject AS subject, a.predicate AS predicate,
                   a.fid AS lf, a.value AS lv, da.id AS ld, da.authority AS la,
                   b.fid AS rf, b.value AS rv, db.id AS rd, db.authority AS ra_
            ORDER BY subject, predicate, lf, rf
            """
        )
        return [
            Contradiction(
                r["subject"], r["predicate"], r["lf"], r["lv"], r["ld"], r["la"],
                r["rf"], r["rv"], r["rd"], r["ra_"],
            )
            for r in rows
        ]

    def answer(self, subject: str, predicate: str) -> dict[str, Any]:
        """Which value is in force, and why. Authority wins; a tie is reported, not hidden."""
        facts = self.current_facts(subject, predicate)
        if not facts:
            return {"status": "unknown", "reason": "no current fact asserted"}
        top = facts[0]
        values = {f["value"] for f in facts}
        if len(values) == 1:
            return {"status": "agreed", "value": top["value"], "sources": [f["rev"] for f in facts]}
        tied = [f for f in facts if f["authority"] == top["authority"] and f["value"] != top["value"]]
        if tied:
            return {"status": "unresolved", "reason": "equal-authority sources disagree",
                    "candidates": facts}
        return {
            "status": "resolved",
            "value": top["value"],
            "source": top["rev"],
            "reason": f"{top['doc']} (authority {top['authority']}) outranks the conflicting source(s)",
            "overruled": [f for f in facts if f["value"] != top["value"]],
        }

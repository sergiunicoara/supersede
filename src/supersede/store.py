"""Supersede: an embedded knowledge store that knows which fact is currently in force.

Built on Relate (embedded graph DB, Cypher, in-process). Core idea: documents have
revisions linked by SUPERSEDES; facts belong to revisions; a contradiction only
counts between facts in *current* (not superseded) revisions, and is resolved by the
authority level of the owning document.
"""
from __future__ import annotations

import os
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import date as _date
from dataclasses import dataclass
from typing import Any

import relate

from .embed import Embedder, HashingEmbedder, content_words


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

    def __init__(self, path: str = ":memory:", read_only: bool = False, embedder: Embedder | None = None,
                 combine: bool = False) -> None:
        """`read_only=True` opens an existing store without taking the writer lock (queries only).

        `embedder` turns topic descriptions and questions into vectors for Relate's vector index (default: the
        dependency-free `HashingEmbedder`). A store remembers which embedder built its vectors.

        `combine=True` opts in to Relate's own `COMBINE` hybrid search (`ask(retrieval="combine")`). It is a
        preview feature of Relate, so this sets `RELATE_PREVIEW=hybrid-search` for the process before connecting.
        """
        self._combine = combine
        if combine:
            flags = [f for f in os.environ.get("RELATE_PREVIEW", "").split(",") if f]
            if "hybrid-search" not in flags:
                os.environ["RELATE_PREVIEW"] = ",".join(flags + ["hybrid-search"])
        self._embedder: Embedder = embedder or HashingEmbedder()
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="relate")
        self._conn = self._pool.submit(relate.connect, path, read_only=read_only).result()

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
    # Writes are strict: a reference to something that does not exist, a reused fact id, a
    # non-integer authority or a cycle in SUPERSEDES raises ValueError instead of silently
    # doing nothing or overwriting another revision's data.
    def _exists(self, label: str, key: str, value: str) -> bool:
        rows = self._run(f"MATCH (n:{label} {{{key}: $v}}) RETURN count(n) AS n", {"v": value})
        return rows[0]["n"] > 0

    def add_document(self, doc_id: str, title: str, authority: int) -> None:
        if isinstance(authority, bool) or not isinstance(authority, int):
            raise ValueError(f"authority of document {doc_id!r} must be an integer, got {authority!r}")
        self._run(
            "MERGE (d:Doc {id: $id}) SET d.title = $title, d.authority = $authority",
            {"id": doc_id, "title": title, "authority": authority},
        )

    def add_revision(self, doc_id: str, rev: int, effective: str) -> str:
        rev_id = f"{doc_id}-r{rev}"
        if not self._exists("Doc", "id", doc_id):
            raise ValueError(f"unknown document {doc_id!r}: call add_document first")
        self._run(
            "MATCH (d:Doc {id: $doc}) "
            "MERGE (r:Rev {id: $rid}) SET r.doc = $doc, r.rev = $rev, r.effective = $eff "
            "MERGE (d)-[:HAS_REV]->(r)",
            {"doc": doc_id, "rid": rev_id, "rev": rev, "eff": effective},
        )
        return rev_id

    def supersede(self, newer_rev: str, older_rev: str) -> None:
        for rid in (newer_rev, older_rev):
            if not self._exists("Rev", "id", rid):
                raise ValueError(f"unknown revision {rid!r}: call add_revision first")
        # adding newer -> older closes a cycle if older can already reach newer (or they are equal)
        cyc = self._run(
            "MATCH (:Rev {id: $o})-[:SUPERSEDES*0..]->(n:Rev {id: $n}) RETURN count(n) AS n",
            {"n": newer_rev, "o": older_rev},
        )
        if cyc[0]["n"] > 0:
            raise ValueError(f"{newer_rev!r} superseding {older_rev!r} would create a cycle")
        self._run(
            "MATCH (a:Rev {id: $n}), (b:Rev {id: $o}) MERGE (a)-[:SUPERSEDES]->(b)",
            {"n": newer_rev, "o": older_rev},
        )

    def add_topic(self, subject: str, predicate: str, description: str) -> None:
        """Describe a (subject, predicate) key in plain language so `ask()` can find it.

        Two Relate indexes are built over the description: a full-text index (BM25) and a vector index over its
        embedding. Include the words a person would use in a question, including synonyms.
        """
        if not description.strip():
            raise ValueError("a topic needs a non-empty description")
        self._run("CREATE FULLTEXT INDEX topic_text IF NOT EXISTS FOR (t:Topic) ON EACH [t.description]")
        self._run(
            "MERGE (t:Topic {key: $k}) SET t.subject = $s, t.predicate = $p, t.description = $d",
            {"k": f"{subject}.{predicate}", "s": subject, "p": predicate, "d": description},
        )
        vec = self._embedder.embed(description)
        if vec is not None:
            dim = int(self._embedder.dim)
            self._run("CREATE VECTOR INDEX topic_vec IF NOT EXISTS FOR (t:Topic) ON (t.embedding) OPTIONS "
                      "{indexConfig: {`vector.dimensions`: " + str(dim) + ", `vector.similarity_function`: 'cosine'}}")
            self._run("MATCH (t:Topic {key: $k}) SET t.embedding = vector($v, " + str(dim) + ", FLOAT32)",
                      {"k": f"{subject}.{predicate}", "v": vec})
            self._run("MERGE (m:Meta {key: 'embedder'}) SET m.name = $n, m.dim = $dim",
                      {"n": self._embedder.name, "dim": dim})

    def derive(self, derived_rev: str, source_rev: str) -> None:
        """Record that `derived_rev` was written from `source_rev`, a revision of ANOTHER document.

        Within one document, use supersede() instead. DERIVED_FROM links must not form a cycle.
        """
        for rid in (derived_rev, source_rev):
            if not self._exists("Rev", "id", rid):
                raise ValueError(f"unknown revision {rid!r}: call add_revision first")
        docs = self._run(
            "MATCH (a:Rev {id: $a}), (b:Rev {id: $b}) RETURN a.doc AS da, b.doc AS db",
            {"a": derived_rev, "b": source_rev},
        )[0]
        if docs["da"] == docs["db"]:
            raise ValueError(f"{derived_rev!r} and {source_rev!r} are revisions of the same document; "
                             f"use supersede() for that")
        cyc = self._run(
            "MATCH (:Rev {id: $s})-[:DERIVED_FROM*0..]->(n:Rev {id: $d}) RETURN count(n) AS n",
            {"d": derived_rev, "s": source_rev},
        )
        if cyc[0]["n"] > 0:
            raise ValueError(f"{derived_rev!r} derived from {source_rev!r} would create a cycle")
        self._run(
            "MATCH (a:Rev {id: $a}), (b:Rev {id: $b}) MERGE (a)-[:DERIVED_FROM]->(b)",
            {"a": derived_rev, "b": source_rev},
        )

    def assert_fact(self, rev_id: str, fact_id: str, subject: str, predicate: str, value: str) -> None:
        if not self._exists("Rev", "id", rev_id):
            raise ValueError(f"unknown revision {rev_id!r}: call add_revision first")
        owners = self._run(
            "MATCH (f:Fact {fid: $f}) OPTIONAL MATCH (r:Rev)-[:ASSERTS]->(f) RETURN r.id AS rev",
            {"f": fact_id},
        )
        if any(o["rev"] not in (None, rev_id) for o in owners):
            raise ValueError(f"fact id {fact_id!r} is already used by another revision; fact ids must be unique")
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
        """Revisions that `rev_id` replaced, nearest first (the whole chain, however long)."""
        rows = self._run(
            "MATCH p=(n:Rev {id: $id})-[:SUPERSEDES*1..]->(o:Rev) WHERE o.id <> n.id "
            "RETURN o.id AS id, length(p) AS hops ORDER BY hops",
            {"id": rev_id},
        )
        return [r["id"] for r in rows]

    def _replacements(self, rev_id: str) -> list[str]:
        """The current revision(s) at the end of the SUPERSEDES chain that replaced `rev_id`."""
        rows = self._run(
            "MATCH (c:Rev)-[:SUPERSEDES*1..]->(:Rev {id: $id}) WHERE NOT (:Rev)-[:SUPERSEDES]->(c) "
            "RETURN DISTINCT c.id AS id ORDER BY id",
            {"id": rev_id},
        )
        return [r["id"] for r in rows]

    def lineage(self, rev_id: str) -> list[dict[str, Any]]:
        """Revisions that `rev_id` was derived from, directly or through a chain, nearest first.

        Each entry says whether that source is still current and, if not, what replaced it.
        """
        rows = self._run(
            "MATCH p=(:Rev {id: $id})-[:DERIVED_FROM*1..]->(s:Rev) "
            "RETURN s.id AS id, length(p) AS hops ORDER BY hops, id",
            {"id": rev_id},
        )
        current = set(self.current_revisions())
        return [
            {"source": r["id"], "hops": r["hops"], "current": r["id"] in current,
             "replaced_by": [] if r["id"] in current else self._replacements(r["id"])}
            for r in rows
        ]

    def stale_derivations(self) -> list[dict[str, Any]]:
        """Current revisions that rest, directly or through a chain, on a source that was superseded."""
        rows = self._run(
            "MATCH p=(r:Rev)-[:DERIVED_FROM*1..]->(s:Rev) "
            "WHERE NOT (:Rev)-[:SUPERSEDES]->(r) AND (:Rev)-[:SUPERSEDES]->(s) "
            "RETURN r.id AS revision, s.id AS source, length(p) AS hops ORDER BY revision, hops, source"
        )
        return [{**r, "replaced_by": self._replacements(r["source"])} for r in rows]

    # -- time: what was in force on a given date ------------------------
    @staticmethod
    def _day(text: Any) -> _date | None:
        """A strict YYYY-MM-DD date, or None for blank or malformed text."""
        try:
            return _date.fromisoformat(str(text)) if text else None
        except ValueError:
            return None

    def date_warnings(self) -> list[dict[str, str]]:
        """Effective-date problems that make a date-based answer unreliable.

        Blank or malformed dates, dates far in the future, and a revision dated earlier than the
        revision it supersedes. Nothing is fixed or guessed: the problems are reported.
        """
        revs = self._run("MATCH (r:Rev) RETURN r.id AS id, r.effective AS eff ORDER BY id")
        eff = {r["id"]: r["eff"] for r in revs}
        out: list[dict[str, str]] = []
        limit = _date.today().replace(year=_date.today().year + 1)
        for rid, e in eff.items():
            d = self._day(e)
            if d is None:
                out.append({"revision": rid, "issue": "missing_date" if not e else "invalid_date",
                            "detail": "no effective date" if not e else f"cannot read {e!r} as YYYY-MM-DD"})
            elif d > limit:
                out.append({"revision": rid, "issue": "future_date", "detail": f"dated {e}, in the future"})
        for e in self._run("MATCH (n:Rev)-[:SUPERSEDES]->(o:Rev) RETURN n.id AS n, o.id AS o ORDER BY n, o"):
            dn, do = self._day(eff.get(e["n"])), self._day(eff.get(e["o"]))
            if dn and do and dn < do:
                out.append({"revision": e["n"], "issue": "dated_before_predecessor",
                            "detail": f"supersedes {e['o']} ({eff[e['o']]}) but is dated {eff[e['n']]}"})
        return out

    def in_force(self, as_of: str) -> set[str]:
        """Revisions in force on `as_of` (YYYY-MM-DD), taking the effective dates at face value.

        A revision is in force if it is dated on or before that day and no revision that supersedes
        it is. A revision without a usable date can never be placed on the timeline, so it is
        neither in force nor able to end its predecessor; `date_warnings()` reports such cases.
        """
        day = self._day(as_of)
        if day is None:
            raise ValueError(f"as_of must be a date like 2025-07-01, got {as_of!r}")
        eff = {r["id"]: self._day(r["eff"]) for r in self._run("MATCH (r:Rev) RETURN r.id AS id, r.effective AS eff")}
        ended: set[str] = set()
        for e in self._run("MATCH (n:Rev)-[:SUPERSEDES]->(o:Rev) RETURN n.id AS n, o.id AS o"):
            if eff.get(e["n"]) is not None and eff[e["n"]] <= day:
                ended.add(e["o"])
        return {rid for rid, d in eff.items() if d is not None and d <= day and rid not in ended}

    def timeline(self, subject: str, predicate: str) -> list[dict[str, Any]]:
        """Every fact stated about (subject, predicate), with when its revision takes effect and when it ends.

        `starts` is the revision's effective date (None if blank or unreadable). `ends` is the earliest valid effective
        date of a revision that supersedes it (None if nothing does, or if the successor has no usable date).
        Sorted by document, then date. Used to draw the timeline; it does not decide what is in force
        (`in_force()` and `answer()` do).
        """
        facts = self._run(
            "MATCH (d:Doc)-[:HAS_REV]->(r:Rev)-[:ASSERTS]->(f:Fact) WHERE f.subject = $s AND f.predicate = $p "
            "RETURN f.fid AS fact, f.value AS value, r.id AS rev, r.effective AS effective, d.id AS doc, "
            "d.authority AS authority ORDER BY doc, effective, rev",
            {"s": subject, "p": predicate},
        )
        eff = {r["id"]: r["eff"] for r in self._run("MATCH (r:Rev) RETURN r.id AS id, r.effective AS eff")}
        successors: dict[str, list[str]] = {}
        for e in self._run("MATCH (n:Rev)-[:SUPERSEDES]->(o:Rev) RETURN n.id AS n, o.id AS o"):
            successors.setdefault(e["o"], []).append(e["n"])
        out = []
        for f in facts:
            ends = sorted(str(d) for d in (self._day(eff.get(n)) for n in successors.get(f["rev"], [])) if d)
            out.append({**f, "starts": str(self._day(f["effective"])) if self._day(f["effective"]) else None,
                        "ends": ends[0] if ends else None, "superseded_by": sorted(successors.get(f["rev"], []))})
        return out

    def topics(self) -> list[dict[str, str]]:
        """The (subject, predicate, description) topics, for pickers and for ask(); empty if there are none."""
        try:
            return self._run("MATCH (t:Topic) RETURN t.subject AS subject, t.predicate AS predicate, "
                             "t.description AS description ORDER BY subject, predicate")
        except Exception:
            return []

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
            MATCH (da:Doc)-[:HAS_REV]->(ra:Rev)-[:ASSERTS]->(a:Fact)
            MATCH (db:Doc)-[:HAS_REV]->(rb:Rev)-[:ASSERTS]->(b:Fact)
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

    def _decide(self, facts: list[dict[str, Any]], none_reason: str) -> dict[str, Any]:
        """Which value wins among facts already sorted by authority. A tie is reported, not hidden."""
        if not facts:
            return {"status": "unknown", "reason": none_reason}
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

    def answer(self, subject: str, predicate: str, as_of: str | None = None) -> dict[str, Any]:
        """Which value is in force, and why. Authority wins; a tie is reported, not hidden.

        With `as_of` (YYYY-MM-DD) it answers for that day instead of today: only revisions in force
        that day count, and any date problem that could affect the answer is reported in
        `warnings` (a blank or wrong date is never guessed).
        """
        if as_of is None:
            return self._decide(self.current_facts(subject, predicate), "no current fact asserted")
        in_force = self.in_force(as_of)
        every = self._run(
            "MATCH (d:Doc)-[:HAS_REV]->(r:Rev)-[:ASSERTS]->(f:Fact) "
            "WHERE f.subject = $s AND f.predicate = $p "
            "RETURN f.fid AS fact, f.value AS value, r.id AS rev, d.id AS doc, d.authority AS authority "
            "ORDER BY authority DESC, fact",
            {"s": subject, "p": predicate},
        )
        result = self._decide([f for f in every if f["rev"] in in_force], f"no fact in force on {as_of}")
        docs = {f["doc"] for f in every}
        warnings = [w for w in self.date_warnings() if w["revision"].rsplit("-r", 1)[0] in docs]
        result["as_of"] = as_of
        if warnings:
            result["warnings"] = warnings
        return result

    # -- retrieval: find the key from a question, then reason over the graph --
    # Vector scores from Relate are (1 + cosine) / 2, so unrelated text sits near 0.5. The threshold below was chosen
    # on eval/calibration.yaml (questions that are not in the evaluation set): see eval/calibrate_vector.py.
    MIN_VECTOR_SCORE = 0.70
    RRF_K = 60  # reciprocal rank fusion constant

    def _fulltext_hits(self, terms: list[str], limit: int) -> list[dict[str, Any]] | None:
        """Topics ranked by BM25 over their descriptions; None if the store has no full-text index."""
        try:
            return self._run(
                "MATCH (t:Topic) SEARCH t IN (FULLTEXT INDEX topic_text FOR $q LIMIT " + str(int(limit)) + ") "
                "SCORE AS score RETURN t.subject AS subject, t.predicate AS predicate, "
                "t.description AS description, score ORDER BY score DESC",
                {"q": " ".join(terms)},
            )
        except Exception as exc:
            if "index" in str(exc).lower():
                return None
            raise

    def _vector_hits(self, question: str, limit: int) -> list[dict[str, Any]] | None:
        """Topics nearest to the question in Relate's vector index; None if unavailable (no index, or the store was
        built with a different embedder), [] if the question has nothing to embed."""
        meta = self._run("MATCH (m:Meta {key: 'embedder'}) RETURN m.name AS name")
        if not meta or meta[0]["name"] != self._embedder.name:
            return None
        vec = self._embedder.embed(question)
        if vec is None:
            return []
        try:
            return self._run(
                "MATCH (t:Topic) SEARCH t IN (VECTOR INDEX topic_vec FOR $v LIMIT " + str(int(limit)) + ") "
                "SCORE AS score RETURN t.subject AS subject, t.predicate AS predicate, "
                "t.description AS description, score ORDER BY score DESC",
                {"v": vec},
            )
        except Exception:
            return None

    def _combine_hits(self, text: str, vec: list[float], limit: int) -> list[dict[str, Any]]:
        """Topics ranked by Relate's own `COMBINE` (weighted reciprocal rank fusion of the full-text and vector
        indexes, equal weights, constant 60). Needs `Store(combine=True)`; raises if Relate rejects the query."""
        return self._run(
            "MATCH (t:Topic) SEARCH t IN (COMBINE ("
            "VECTOR INDEX topic_vec FOR $v LIMIT $n WEIGHT 1, FULLTEXT INDEX topic_text FOR $q LIMIT $n WEIGHT 1) "
            "USING WRRF WITH CONSTANT 60 LIMIT $n) SCORE AS score "
            "RETURN t.subject AS subject, t.predicate AS predicate, t.description AS description, score "
            "ORDER BY score DESC",
            {"v": vec, "q": text, "n": int(limit)},
        )

    def ask(self, question: str, k: int = 3, as_of: str | None = None, retrieval: str = "hybrid") -> dict[str, Any]:
        """Answer a plain-language question: retrieval finds the topic, the graph decides the value.

        Retrieval uses two Relate indexes over the topic descriptions: full-text (BM25, exact words) and vector
        (hashed word and character n-grams, which tolerate plurals, tenses and typos). `retrieval` is "hybrid" (the
        default: both, fused by reciprocal rank), "fulltext", "vector", or "combine" (the same two indexes fused by
        Relate's own preview `COMBINE`; needs `Store(combine=True)`). The best topic is answered with `answer()`,
        so supersession, authority, ties and dates all apply, and the answer says if the revisions it rests on were
        written from a source that has since been superseded. A store built without vectors falls back to full-text.
        """
        if retrieval not in ("hybrid", "fulltext", "vector", "combine"):
            raise ValueError("retrieval must be 'hybrid', 'fulltext', 'vector' or 'combine'")
        if retrieval == "combine" and not self._combine:
            raise ValueError("retrieval='combine' uses a Relate preview feature: open the store with Store(combine=True)")
        if as_of is not None and self._day(as_of) is None:
            raise ValueError(f"as_of must be a date like 2025-07-01, got {as_of!r}")
        terms = content_words(question)
        if not terms:
            return {"question": question, "status": "no_match", "reason": "the question has no searchable words"}
        ft = self._fulltext_hits(terms, 10) if retrieval in ("hybrid", "fulltext", "combine") else []
        vh = self._vector_hits(question, 10) if retrieval in ("hybrid", "vector", "combine") else []
        if ft is None and not vh:
            return {"question": question, "status": "no_topics",
                    "reason": "this store has no topic descriptions; add them with Store.add_topic()"}
        ranked: dict[str, dict[str, Any]] = {}

        def add(hit: dict[str, Any], rank: int, field: str, value: float) -> None:
            r = ranked.setdefault(f"{hit['subject']}.{hit['predicate']}", {**hit, "rrf": 0.0, "fulltext_rank": None,
                                                                          "vector_score": None})
            r["rrf"] += 1.0 / (self.RRF_K + rank)
            r[field] = value

        if retrieval == "combine":
            # Relate does the ranking. It has no minimum score, so the same gate as "hybrid" decides which results
            # count: a full-text hit, or a vector score of at least MIN_VECTOR_SCORE.
            if vh is None:
                return {"question": question, "status": "no_topics",
                        "reason": "COMBINE needs the vector index built by this store's embedder"}
            ft_rank = {f"{h['subject']}.{h['predicate']}": i for i, h in enumerate(ft or [], 1)}
            vscore = {f"{h['subject']}.{h['predicate']}": h["score"] for h in vh}
            for h in self._combine_hits(" ".join(terms), self._embedder.embed(question), 10):
                key = f"{h['subject']}.{h['predicate']}"
                if key in ft_rank or vscore.get(key, 0.0) >= self.MIN_VECTOR_SCORE:
                    ranked[key] = {**h, "rrf": h["score"], "fulltext_rank": ft_rank.get(key),
                                   "vector_score": round(vscore[key], 3) if key in vscore else None}
        for rank, h in enumerate(ft or [] if retrieval != "combine" else [], 1):
            add(h, rank, "fulltext_rank", rank)
        for rank, h in enumerate([h for h in (vh or []) if h["score"] >= self.MIN_VECTOR_SCORE]
                                 if retrieval != "combine" else [], 1):
            add(h, rank, "vector_score", round(h["score"], 3))
        if not ranked:
            return {"question": question, "status": "no_match", "reason": "no topic matches the question"}
        order = sorted(ranked.values(), key=lambda r: -r["rrf"])
        best = order[0]
        ans = self.answer(best["subject"], best["predicate"], as_of)
        sources = set(ans.get("sources", [])) | ({ans["source"]} if "source" in ans else set()) \
            | {c["rev"] for c in ans.get("candidates", [])}
        stale = [d for d in self.stale_derivations() if d["revision"] in sources]
        out: dict[str, Any] = {
            "question": question,
            "status": ans["status"],
            "matched": {"subject": best["subject"], "predicate": best["predicate"],
                        "description": best["description"], "score": round(best["rrf"], 4),
                        "via": {"mode": retrieval, "fulltext_rank": best["fulltext_rank"],
                                "vector_score": best["vector_score"]}},
            "answer": ans,
            "alternatives": [{"subject": h["subject"], "predicate": h["predicate"], "score": round(h["rrf"], 4)}
                             for h in order[1:k]],
        }
        if stale:
            out["stale_sources"] = stale
        return out

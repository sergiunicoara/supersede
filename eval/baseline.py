"""Naive baseline: no graph structure.

Ignores SUPERSEDES and document authority. For a (subject, predicate) it looks at every fact
asserted by every revision of every document and returns the one from the most recent
`effective` date. Ties on date are broken by fact id (the corpus has none). It cannot report
disagreement: it always returns a value when any fact matches.
"""
from __future__ import annotations


def answer(docs: list[dict], subject: str, predicate: str) -> dict:
    hits = [
        (r["effective"], f["id"], f["value"], f"{d['id']}-r{r['rev']}")
        for d in docs
        for r in d["revisions"]
        for f in r["facts"]
        if f["subject"] == subject and f["predicate"] == predicate
    ]
    if not hits:
        return {"status": "unknown"}
    _, _, value, source = max(hits)
    return {"status": "answered", "value": value, "source": source}

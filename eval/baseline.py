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


# --- ablations: each keeps ONE part of the graph structure, to show what each part buys -----
def _facts(docs: list[dict], subject: str, predicate: str, current_only: bool):
    superseded = {f"{d['id']}-r{r['supersedes']}" for d in docs for r in d["revisions"] if "supersedes" in r}
    for d in docs:
        for r in d["revisions"]:
            rid = f"{d['id']}-r{r['rev']}"
            if current_only and rid in superseded:
                continue
            for f in r["facts"]:
                if f["subject"] == subject and f["predicate"] == predicate:
                    yield d["authority"], r["effective"], f["id"], f["value"], rid


def _pick(hits: list, key) -> dict:
    if not hits:
        return {"status": "unknown"}
    h = max(hits, key=key)
    return {"status": "answered", "value": h[3], "source": h[4]}


def answer_supersession_aware(docs: list[dict], subject: str, predicate: str) -> dict:
    """Follows SUPERSEDES (skips superseded revisions) but ignores authority; newest date among the rest."""
    return _pick(list(_facts(docs, subject, predicate, True)), key=lambda h: (h[1], h[2]))


def answer_authority_aware(docs: list[dict], subject: str, predicate: str) -> dict:
    """Uses document authority but ignores SUPERSEDES; highest authority, then newest date."""
    return _pick(list(_facts(docs, subject, predicate, False)), key=lambda h: (h[0], h[1], h[2]))

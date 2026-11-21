"""Load annotated Markdown documents into a Store.

One file per document revision. A small header carries the metadata, and facts are marked inline
in the prose with ``{{subject.predicate = value}}``:

    ---
    doc: QP-40
    title: Packaging procedure
    authority: 3
    revision: 2
    effective: 2025-10-01
    supersedes: 1            # optional: the revision number of the same document it replaces
    derived_from: QP-07-r1   # optional: revision(s) of OTHER documents it was written from
    ---
    Parts are packed {{packaging.units_per_box = 24}} to a box, labelled in
    {{packaging.label_language = English and German}}.

This is deterministic: it reads facts that an author has marked, it does not extract facts from
unannotated text. It needs no dependencies beyond the standard library.

Usage:  python -m supersede.ingest DIR --db PATH     (PATH must not exist yet)
"""
from __future__ import annotations

import argparse
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path

from .store import Store

_FACT = re.compile(r"\{\{\s*([A-Za-z0-9_\-]+)\.([A-Za-z0-9_\-]+)\s*=\s*(.+?)\s*\}\}")
_HEADER = ("doc", "title", "authority", "revision", "effective")


@dataclass(frozen=True)
class Revision:
    doc: str
    title: str
    authority: int
    rev: int
    effective: str
    supersedes: int | None
    facts: tuple[tuple[str, str, str], ...]  # (subject, predicate, value)
    source: str
    derived_from: tuple[str, ...] = ()       # revision ids such as "QP-07-r1"


def parse(text: str, source: str = "<text>") -> Revision:
    """Parse one annotated Markdown document revision."""
    lines = text.lstrip("﻿").replace("\r\n", "\n").split("\n")
    if not lines or lines[0].strip() != "---":
        raise ValueError(f"{source}: the file must start with a '---' header")
    try:
        end = lines.index("---", 1)
    except ValueError:
        raise ValueError(f"{source}: the header is not closed with '---'") from None
    meta: dict[str, str] = {}
    for raw in lines[1:end]:
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        if ":" not in line:
            raise ValueError(f"{source}: bad header line {raw!r}")
        key, value = line.split(":", 1)
        meta[key.strip()] = value.strip()
    missing = [k for k in _HEADER if not meta.get(k)]
    if missing:
        raise ValueError(f"{source}: missing header field(s): {', '.join(missing)}")
    try:
        authority, rev = int(meta["authority"]), int(meta["revision"])
        supersedes = int(meta["supersedes"]) if meta.get("supersedes") else None
    except ValueError:
        raise ValueError(f"{source}: authority, revision and supersedes must be integers") from None
    body = "\n".join(lines[end + 1:])
    facts = tuple((m.group(1), m.group(2), m.group(3)) for m in _FACT.finditer(body))
    derived = tuple(x.strip() for x in meta.get("derived_from", "").split(",") if x.strip())
    return Revision(meta["doc"], meta["title"], authority, rev, meta["effective"], supersedes, facts,
                    source, derived)


def split_document(text: str, source: str = "<text>") -> tuple[str, str]:
    """Split a document into (header block including both '---' lines, body)."""
    lines = text.lstrip("\ufeff").replace("\r\n", "\n").split("\n")
    if not lines or lines[0].strip() != "---":
        raise ValueError(f"{source}: the file must start with a '---' header")
    try:
        end = lines.index("---", 1)
    except ValueError:
        raise ValueError(f"{source}: the header is not closed with '---'") from None
    return "\n".join(lines[: end + 1]) + "\n", "\n".join(lines[end + 1:])


def ingest_directory(store: Store, directory: str | os.PathLike,
                     topics: dict[str, str] | None = None) -> tuple[int, int, int]:
    """Load every ``*.md`` file in `directory`. Returns (documents, revisions, facts).

    `topics` ({"subject.predicate": "description"}) makes the store searchable with Store.ask().
    """
    revisions = [parse(p.read_text(encoding="utf-8"), p.name) for p in sorted(Path(directory).glob("*.md"))]
    if not revisions:
        raise ValueError(f"no *.md documents found in {directory}")
    return load_revisions(store, revisions, topics)


def load_revisions(store: Store, revisions: list[Revision],
                   topics: dict[str, str] | None = None) -> tuple[int, int, int]:
    """Validate and load parsed revisions. Returns (documents, revisions, facts)."""
    authority: dict[str, tuple[int, str]] = {}
    seen: set[tuple[str, int]] = set()
    for r in revisions:
        if (r.doc, r.rev) in seen:
            raise ValueError(f"{r.source}: revision {r.rev} of {r.doc} appears twice")
        seen.add((r.doc, r.rev))
        if authority.setdefault(r.doc, (r.authority, r.source))[0] != r.authority:
            raise ValueError(f"{r.source}: {r.doc} has authority {r.authority}, but {authority[r.doc][1]} says "
                             f"{authority[r.doc][0]}")
        if r.supersedes is not None and (r.doc, r.supersedes) not in {(x.doc, x.rev) for x in revisions}:
            raise ValueError(f"{r.source}: supersedes revision {r.supersedes} of {r.doc}, which was not found")
        known = {f"{x.doc}-r{x.rev}" for x in revisions}
        for src in r.derived_from:
            if src not in known:
                raise ValueError(f"{r.source}: derived_from {src!r}, which was not found")
    for r in revisions:
        store.add_document(r.doc, r.title, r.authority)
    ordered = sorted(revisions, key=lambda r: (r.doc, r.rev))
    n_facts = 0
    for r in ordered:
        rid = store.add_revision(r.doc, r.rev, r.effective)
        for i, (subject, predicate, value) in enumerate(r.facts, 1):
            store.assert_fact(rid, f"F-{r.doc}-{r.rev}-{i}", subject, predicate, value)
            n_facts += 1
    for r in ordered:
        if r.supersedes is not None:
            store.supersede(f"{r.doc}-r{r.rev}", f"{r.doc}-r{r.supersedes}")
    for r in ordered:
        for src in r.derived_from:
            store.derive(f"{r.doc}-r{r.rev}", src)
    for key, description in (topics or {}).items():
        subject, predicate = key.split(".", 1)
        store.add_topic(subject, predicate, description)
    store.commit()
    return len(authority), len(revisions), n_facts


def main() -> None:
    ap = argparse.ArgumentParser(description="Load annotated Markdown documents into a new Relate store.")
    ap.add_argument("directory", help="folder with one *.md file per document revision")
    ap.add_argument("--db", required=True, help="path of the new store (must not exist)")
    ap.add_argument("--topics", help='JSON file {"subject.predicate": "description"}: makes the store '
                                     "searchable with ask() (the extraction vocabulary has this shape)")
    args = ap.parse_args()
    if os.path.exists(args.db):
        ap.error(f"{args.db} already exists; pass a new path (this never merges into a store)")
    store = Store(args.db)
    try:
        topics = json.loads(Path(args.topics).read_text(encoding="utf-8")) if args.topics else None
        d, r, f = ingest_directory(store, args.directory, topics)
    finally:
        store.close()
    print(f"ingested {d} documents, {r} revisions, {f} facts into {args.db}")


if __name__ == "__main__":
    main()

"""Load the FICTIONAL automotive-quality corpus (examples/corpus/*.yaml) into a Relate store.

Usage:  python examples/load_corpus.py [path]      (default: demo.relate)

Refuses to load into a path that already exists, so it never mixes into another store
(for example one made by seed_demo.py).
"""
from __future__ import annotations

import pathlib
import sys

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from supersede.store import Store  # noqa: E402

CORPUS_DIR = pathlib.Path(__file__).resolve().parent / "corpus"


def read_corpus(directory: pathlib.Path = CORPUS_DIR) -> list[dict]:
    """Read and validate one document per YAML file. Values are coerced to str."""
    docs = []
    seen_facts: set[str] = set()
    for path in sorted(pathlib.Path(directory).glob("*.yaml")):
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
        rev_numbers = {r["rev"] for r in doc["revisions"]}
        for r in doc["revisions"]:
            r["effective"] = str(r["effective"])
            if "supersedes" in r and r["supersedes"] not in rev_numbers:
                raise ValueError(f"{path.name}: rev {r['rev']} supersedes a missing revision")
            for f in r["facts"]:
                if f["id"] in seen_facts:
                    raise ValueError(f"{path.name}: duplicate fact id {f['id']}")
                seen_facts.add(f["id"])
                f["value"] = str(f["value"])
        docs.append(doc)
    return docs


def load_docs(store: Store, docs: list[dict]) -> None:
    for d in docs:
        store.add_document(d["id"], d["title"], d["authority"])
        for r in d["revisions"]:
            rid = store.add_revision(d["id"], r["rev"], r["effective"])
            for f in r["facts"]:
                store.assert_fact(rid, f["id"], f["subject"], f["predicate"], f["value"])
        for r in d["revisions"]:
            if "supersedes" in r:
                store.supersede(f"{d['id']}-r{r['rev']}", f"{d['id']}-r{r['supersedes']}")
    store.commit()


def counts(docs: list[dict]) -> tuple[int, int, int]:
    revs = sum(len(d["revisions"]) for d in docs)
    facts = sum(len(r["facts"]) for d in docs for r in d["revisions"])
    return len(docs), revs, facts


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "demo.relate"
    if pathlib.Path(target).exists():
        sys.exit(f"{target} already exists; pass a new path (this script never merges into a store)")
    corpus = read_corpus()
    s = Store(target)
    load_docs(s, corpus)
    s.close()
    d, r, f = counts(corpus)
    print(f"loaded {d} documents, {r} revisions, {f} facts into {target}")

"""Full-text vs vector vs hybrid (my fusion) vs combine (Relate's own preview COMBINE) retrieval, on three question sets
(answers must be exactly right: key, status, value).

`retrieval` (23) is the original set. `retrieval_variants` (18) rewords questions (word forms, typos).
`retrieval_synonyms` (20) uses true synonyms and paraphrases; it was written before the model embedder was run on it.

    python eval/compare_retrieval.py                    # the default dependency-free hashing embedder
    python eval/compare_retrieval.py --embedder model   # the optional trained model (needs: pip install fastembed)
"""
from __future__ import annotations

import argparse
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import run_eval  # noqa: E402

MODES = ("fulltext", "vector", "hybrid", "combine")
SECTIONS = ("retrieval", "retrieval_variants", "retrieval_synonyms")


def make_embedder(name: str):
    if name == "hash":
        return None
    from supersede.embed_model import FastEmbedEmbedder
    return FastEmbedEmbedder()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--embedder", choices=("hash", "model"), default="hash")
    args = ap.parse_args()
    emb = make_embedder(args.embedder)
    print(f"embedder: {args.embedder}" + (f" ({emb.name}, min score {getattr(emb, 'min_score', 'default')})" if emb else ""))
    table = {}
    for sec in SECTIONS:
        for mode in MODES:
            table[sec, mode] = run_eval.evaluate_retrieval(section=sec, mode=mode, embedder=emb)
    print(f"{'set':<24}" + "".join(f"{m:>11}" for m in MODES))
    totals = dict.fromkeys(MODES, 0)
    for sec in SECTIONS:
        n = len(table[sec, MODES[0]])
        row = []
        for m in MODES:
            ok = sum(r["ok"] for r in table[sec, m])
            totals[m] += ok
            row.append(f"{ok:>8}/{n}")
        print(f"{sec + f' ({n})':<24}" + "".join(row))
    n_all = sum(len(table[s, MODES[0]]) for s in SECTIONS)
    print(f"{'total (' + str(n_all) + ')':<24}" + "".join(f"{totals[m]:>8}/{n_all}" for m in MODES))
    for sec in SECTIONS:
        for mode in MODES:
            for r in table[sec, mode]:
                if not r["ok"]:
                    q = r["q"]
                    print(f"  miss [{sec}/{mode}] {q['id']}: {q['question']!r} -> {r['got_key']} (want {q['expected_key']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())

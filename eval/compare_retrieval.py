"""Full-text vs vector vs hybrid retrieval on both question sets (answers must be exactly right: key, status, value).

`retrieval` (23) is the original set. `retrieval_variants` (18) rewords questions (word forms, synonyms, typos);
it was written before any of these three modes was run on it. Run:  python eval/compare_retrieval.py
"""
from __future__ import annotations

import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import run_eval  # noqa: E402

MODES = ("fulltext", "vector", "hybrid")
SECTIONS = ("retrieval", "retrieval_variants")


def main() -> int:
    table = {}
    for sec in SECTIONS:
        for mode in MODES:
            table[sec, mode] = run_eval.evaluate_retrieval(section=sec, mode=mode)
    print(f"{'set':<20}" + "".join(f"{m:>11}" for m in MODES))
    for sec in SECTIONS:
        n = len(table[sec, MODES[0]])
        print(f"{sec + f' ({n})':<20}" + "".join(f"{sum(r['ok'] for r in table[sec, m]):>8}/{n}" for m in MODES))
    for sec in SECTIONS:
        for mode in MODES:
            for r in table[sec, mode]:
                if not r["ok"]:
                    q = r["q"]
                    print(f"  miss [{sec}/{mode}] {q['id']}: {q['question']!r} -> {r['got_key']} (want {q['expected_key']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())

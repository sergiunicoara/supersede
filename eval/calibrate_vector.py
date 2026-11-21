"""Choose Store.MIN_VECTOR_SCORE from eval/calibration.yaml (questions that are NOT in eval/questions.yaml).

For every threshold it counts on-topic questions whose correct topic ranks first and scores at or above it, and
off-topic questions whose best vector score is below it. Run:  python eval/calibrate_vector.py
"""
from __future__ import annotations

import pathlib
import sys

import yaml

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "src"))
sys.path.insert(0, str(HERE.parent / "examples"))
from load_corpus import CORPUS_DIR, load_docs, read_corpus, read_topics  # noqa: E402

from supersede.store import Store  # noqa: E402


def scores() -> tuple[list[tuple[str, bool, float]], list[float]]:
    cal = yaml.safe_load((HERE / "calibration.yaml").read_text(encoding="utf-8"))
    store = Store()
    try:
        load_docs(store, read_corpus(CORPUS_DIR), read_topics(CORPUS_DIR))
        on = []
        for it in cal["on_topic"]:
            hits = store._vector_hits(it["question"], 10) or []
            top = hits[0] if hits else None
            on.append((it["question"], bool(top) and f"{top['subject']}.{top['predicate']}" == it["key"],
                       top["score"] if top else 0.0))
        off = []
        for q in cal["off_topic"]:
            hits = store._vector_hits(q, 10) or []
            off.append(hits[0]["score"] if hits else 0.0)
        return on, off
    finally:
        store.close()


def main() -> int:
    on, off = scores()
    right = [sc for _, ok, sc in on if ok]
    print(f"on-topic: {len(right)}/{len(on)} have the right topic first; their scores: "
          f"{min(right):.3f}..{max(right):.3f}" if right else "no on-topic hit")
    for q, ok, sc in on:
        if not ok:
            print(f"  wrong topic first: {q!r} ({sc:.3f})")
    print(f"off-topic best scores: {min(off):.3f}..{max(off):.3f}")
    print(f"\n{'threshold':>9} {'on-topic kept':>14} {'off-topic rejected':>19}")
    best = None
    for t in [x / 100 for x in range(55, 90, 2)]:
        kept = sum(1 for _, ok, sc in on if ok and sc >= t)
        rej = sum(1 for sc in off if sc < t)
        print(f"{t:>9.2f} {kept:>10}/{len(on)} {rej:>15}/{len(off)}")
        if best is None or (kept + rej, -t) > best[0]:
            best = ((kept + rej, -t), t)
    print(f"\nbest total on this set: {best[1]:.2f}  (Store.MIN_VECTOR_SCORE is {Store.MIN_VECTOR_SCORE})")
    return 0


if __name__ == "__main__":
    sys.exit(main())

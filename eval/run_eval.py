"""Run the measured question set against Supersede and a naive baseline.

Usage:  python eval/run_eval.py

Loads examples/corpus into a fresh in-memory store, asks every question in
eval/questions.yaml through Store.answer(), and runs the same questions through
eval/baseline.py. Exit code is non-zero if any Supersede answer is wrong.

Scoring
  Supersede: status must match; if a value is expected it must match; for `resolved` the
             source must equal expected_source; for `agreed` expected_source must be among
             the answer's sources.
  Baselines: three, all scored the same way. "newest date" (eval/baseline.py: ignores SUPERSEDES and
             authority) is the headline baseline. Two ablations each keep one part of the graph:
             "supersession-aware" (skips superseded revisions, ignores authority) and
             "authority-aware" (uses document authority, ignores SUPERSEDES).
             Scored on the VALUE only, which is generous to it (it has no status or reason):
             - expected unknown    -> passes if it also finds nothing
             - expected unresolved -> never passes: it cannot report a disagreement, it always
                                      guesses one value
             - otherwise           -> passes if its value equals expected_value
"""
from __future__ import annotations

import pathlib
import sys
from collections import OrderedDict

import yaml

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "examples"))
sys.path.insert(0, str(HERE.parent / "src"))

import baseline  # noqa: E402
from load_corpus import CORPUS_DIR, counts, load_docs, read_corpus  # noqa: E402
from supersede.store import Store  # noqa: E402

QUESTIONS = HERE / "questions.yaml"


def check_supersede(q: dict, got: dict) -> bool:
    if got.get("status") != q["expected_status"]:
        return False
    if "expected_value" in q and got.get("value") != q["expected_value"]:
        return False
    src = q.get("expected_source")
    if src is not None:
        if q["expected_status"] == "resolved" and got.get("source") != src:
            return False
        if q["expected_status"] == "agreed" and src not in got.get("sources", []):
            return False
    return True


def check_baseline(q: dict, got: dict) -> bool:
    if q["expected_status"] == "unknown":
        return got["status"] == "unknown"
    if q["expected_status"] == "unresolved":
        return False
    return got.get("value") == q.get("expected_value")


def evaluate(corpus_dir=CORPUS_DIR, questions_path=QUESTIONS) -> list[dict]:
    docs = read_corpus(corpus_dir)
    questions = yaml.safe_load(pathlib.Path(questions_path).read_text(encoding="utf-8"))["questions"]
    store = Store()  # fresh in-memory store
    load_docs(store, docs)
    rows = []
    try:
        for q in questions:
            got = store.answer(q["subject"], q["predicate"])
            base = baseline.answer(docs, q["subject"], q["predicate"])
            sup = baseline.answer_supersession_aware(docs, q["subject"], q["predicate"])
            aut = baseline.answer_authority_aware(docs, q["subject"], q["predicate"])
            rows.append({
                "q": q, "got": got, "base": base,
                "ok": check_supersede(q, got), "base_ok": check_baseline(q, base),
                "sup_ok": check_baseline(q, sup), "aut_ok": check_baseline(q, aut),
            })
    finally:
        store.close()
    return rows


def evaluate_lineage(corpus_dir=CORPUS_DIR, questions_path=QUESTIONS) -> list[dict]:
    """Cross-document lineage checks (DERIVED_FROM). Only Supersede is scored: the baselines keep no
    derivation structure, so there is nothing for them to answer."""
    docs = read_corpus(corpus_dir)
    items = yaml.safe_load(pathlib.Path(questions_path).read_text(encoding="utf-8")).get("lineage", [])
    store = Store()
    load_docs(store, docs)
    rows = []
    try:
        for it in items:
            got = store.stale_derivations() if it["ask"] == "stale_derivations" else store.lineage(it["revision"])
            rows.append({"item": it, "got": got, "ok": got == it["expected"]})
    finally:
        store.close()
    return rows


def _show(got: dict) -> str:
    if got["status"] == "unknown":
        return "unknown"
    if got["status"] == "unresolved":
        return "unresolved"
    return f"{got['status']}: {got['value']}" if "value" in got else got["status"]


def main() -> int:
    docs = read_corpus()
    d, r, f = counts(docs)
    rows = evaluate()
    print(f"Corpus: {d} documents, {r} revisions, {f} facts (fictional)\n")
    print(f"{'id':<4} {'case':<13} {'question':<44} {'expected':<22} {'Supersede':<5} {'Baseline':<5}  baseline said")
    for x in rows:
        q = x["q"]
        exp = q["expected_status"] + (f": {q['expected_value']}" if "expected_value" in q else "")
        base_said = x["base"].get("value", x["base"]["status"])
        print(f"{q['id']:<4} {q['case']:<13} {q['subject'] + ' / ' + q['predicate']:<44} {exp:<22} "
              f"{'PASS' if x['ok'] else 'FAIL':<9} {'PASS' if x['base_ok'] else 'FAIL':<8}  {base_said}")
    by_case: "OrderedDict[str, list[int]]" = OrderedDict()
    for x in rows:
        c = by_case.setdefault(x["q"]["case"], [0, 0, 0, 0, 0])
        c[0] += 1
        c[1] += x["ok"]
        c[2] += x["base_ok"]
        c[3] += x["sup_ok"]
        c[4] += x["aut_ok"]
    n = len(rows)
    s_ok, b_ok = sum(x["ok"] for x in rows), sum(x["base_ok"] for x in rows)
    sup_ok, aut_ok = sum(x["sup_ok"] for x in rows), sum(x["aut_ok"] for x in rows)
    print(f"\n{'case':<13} {'questions':>9} {'Supersede':>10} {'newest date':>12} {'supersession-aware':>19} {'authority-aware':>16}")
    for case, (t, s, b, su, au) in by_case.items():
        print(f"{case:<13} {t:>9} {s:>6}/{t:<3} {b:>8}/{t:<3} {su:>14}/{t:<4} {au:>12}/{t:<3}")
    print(f"{'TOTAL':<13} {n:>9} {s_ok:>6}/{n:<3} {b_ok:>8}/{n:<3} {sup_ok:>14}/{n:<4} {aut_ok:>12}/{n:<3}")
    print(f"\nSupersede: {s_ok}/{n} passed.  Baseline (newest effective date, no graph): {b_ok}/{n} passed.")
    print(f"Ablations: supersession-aware only {sup_ok}/{n}, authority-aware only {aut_ok}/{n}.")
    lin = evaluate_lineage()
    print(f"\nLineage (DERIVED_FROM chains across documents): Supersede {sum(x['ok'] for x in lin)}/{len(lin)}"
          f"  [{', '.join(x['item']['id'] + ' ' + ('PASS' if x['ok'] else 'FAIL') for x in lin)}]"
          "  (baselines: not applicable, they keep no derivation structure)")
    return 0 if s_ok == n and all(x["ok"] for x in lin) else 1


if __name__ == "__main__":
    sys.exit(main())

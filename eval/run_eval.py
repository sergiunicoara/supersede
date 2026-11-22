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
import re
import sys
from collections import OrderedDict

import yaml

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "examples"))
sys.path.insert(0, str(HERE.parent / "src"))

import baseline  # noqa: E402
from load_corpus import CORPUS_DIR, counts, load_docs, read_corpus, read_topics  # noqa: E402
from supersede.embed import STOPWORDS  # noqa: E402
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


def _loaded(corpus_dir, combine: bool = False, embedder=None) -> tuple[list[dict], Store]:
    docs = read_corpus(corpus_dir)
    store = Store(combine=combine, embedder=embedder)
    load_docs(store, docs, read_topics(corpus_dir))
    return docs, store


def _name_overlap_key(question: str, keys: list[str]) -> str | None:
    """Naive retrieval: the key whose NAME shares the most words with the question (no index, no descriptions)."""
    words = {w for w in re.findall(r"[a-z0-9]+", question.lower()) if w not in STOPWORDS}
    best, best_n = None, 0
    for k in sorted(keys):
        n = len(words & set(re.split(r"[_.]", k)))
        if n > best_n:
            best, best_n = k, n
    return best


def _baseline_value_ok(q: dict, key: str | None, docs: list[dict]) -> bool:
    """Newest-date answer for a retrieved key, scored like the other baselines (value only)."""
    if key is None:
        return q["expected_status"] == "no_match"
    if q["expected_status"] == "no_match" or key != q["expected_key"]:
        return False
    subject, predicate = key.split(".", 1)
    return check_baseline(q, baseline.answer(docs, subject, predicate))


def evaluate_retrieval(corpus_dir=CORPUS_DIR, questions_path=QUESTIONS, section="retrieval", mode="hybrid",
                       embedder=None) -> list[dict]:
    """Plain-language questions through ask(). Compares Relate hybrid retrieval + graph reasoning with
    (a) the same retrieval answered by newest date and (b) name-overlap retrieval answered by newest date."""
    items = yaml.safe_load(pathlib.Path(questions_path).read_text(encoding="utf-8")).get(section, [])
    docs, store = _loaded(corpus_dir, combine=mode == "combine", embedder=embedder)
    keys = sorted(read_topics(corpus_dir))
    rows = []
    try:
        for q in items:
            res = store.ask(q["question"], retrieval=mode)
            m = res.get("matched")
            key = f"{m['subject']}.{m['predicate']}" if m else None
            ans = res.get("answer", {})
            key_ok = key == q["expected_key"]
            answer_ok = key_ok and res["status"] == q["expected_status"] and (
                "expected_value" not in q or ans.get("value") == q["expected_value"])
            if q["expected_key"] is None:
                answer_ok = res["status"] == "no_match"
            naive_key = _name_overlap_key(q["question"], keys)
            rows.append({
                "q": q, "got_key": key, "key_ok": key_ok, "ok": answer_ok,
                "same_retrieval_newest_ok": _baseline_value_ok(q, key, docs),
                "naive_key_ok": naive_key == q["expected_key"],
                "naive_ok": _baseline_value_ok(q, naive_key, docs),
            })
    finally:
        store.close()
    return rows


def _newest_fact_before(docs: list[dict], subject: str, predicate: str, day: str) -> dict:
    """Date-only baseline: the newest dated fact on or before `day`, ignoring SUPERSEDES and authority."""
    hits = [(r["effective"], f["id"], f["value"]) for d in docs for r in d["revisions"] for f in r["facts"]
            if f["subject"] == subject and f["predicate"] == predicate and r["effective"] and r["effective"] <= day]
    if not hits:
        return {"status": "unknown"}
    return {"status": "answered", "value": max(hits)[2]}


def check_as_of(q: dict, got: dict) -> bool:
    if got.get("status") != q["expected_status"]:
        return False
    if "expected_value" in q and got.get("value") != q["expected_value"]:
        return False
    src = q.get("expected_source")
    if src is not None and src != got.get("source") and src not in got.get("sources", []):
        return False
    return {w["issue"] for w in got.get("warnings", [])} == set(q.get("expected_warnings", []))


def evaluate_as_of(corpus_dir=CORPUS_DIR, questions_path=QUESTIONS) -> list[dict]:
    items = yaml.safe_load(pathlib.Path(questions_path).read_text(encoding="utf-8")).get("as_of", [])
    docs, store = _loaded(corpus_dir)
    rows = []
    try:
        for q in items:
            got = store.answer(q["subject"], q["predicate"], as_of=q["date"])
            base = _newest_fact_before(docs, q["subject"], q["predicate"], q["date"])
            rows.append({"q": q, "got": got, "ok": check_as_of(q, got), "base_ok": check_baseline(q, base)})
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

    ret = evaluate_retrieval()
    nr = len(ret)
    print(f"\nPlain-language questions through ask() ({nr}; {sum(1 for x in ret if x['q']['expected_key'] is None)} are off-topic):")
    print(f"  retrieval, right topic first:  Relate hybrid (full-text + vector) {sum(x['key_ok'] for x in ret)}/{nr}"
          f"   name-overlap baseline {sum(x['naive_key_ok'] for x in ret)}/{nr}")
    print(f"  answer correct end to end:     ask() {sum(x['ok'] for x in ret)}/{nr}"
          f"   same retrieval + newest date {sum(x['same_retrieval_newest_ok'] for x in ret)}/{nr}"
          f"   name-overlap + newest date {sum(x['naive_ok'] for x in ret)}/{nr}")
    for x in ret:
        if not x["ok"]:
            print(f"    ask() missed {x['q']['id']}: {x['q']['question']!r} -> topic {x['got_key']} (expected {x['q']['expected_key']})")
    asof = evaluate_as_of()
    na = len(asof)
    print(f"\nWhat was in force on a date ({na}): Supersede {sum(x['ok'] for x in asof)}/{na}"
          f"   newest fact on or before the date {sum(x['base_ok'] for x in asof)}/{na}")
    for x in asof:
        if not x["ok"]:
            print(f"    as-of missed {x['q']['id']}: {x['got']}")
    return 0 if s_ok == n and all(x["ok"] for x in lin) and all(x["ok"] for x in asof) else 1


if __name__ == "__main__":
    sys.exit(main())

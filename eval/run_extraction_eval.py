"""Measure automatic fact extraction on the unannotated example documents (LIVE: calls the API).

Usage:  ANTHROPIC_API_KEY=... python eval/run_extraction_eval.py [--dir examples/real] [--model M]

--dir picks the document folder (default examples/documents_raw; examples/real holds real federal
regulation text). Each folder has its own vocabulary.json and gold.json.

For each document in examples/documents_raw/ it extracts facts with the vocabulary guard rails
(src/supersede/extract.py) and compares them with examples/documents_raw/gold.json, which was written
from the documents BEFORE any model was run. It reports:

  * precision / recall per document and in total (a fact counts as right only if the key AND the
    value, compared case- and whitespace-insensitively, match the gold fact);
  * how many model outputs the guard rails rejected, and why;
  * the end-to-end check: load the gold facts and the extracted facts into two graphs and compare
    `Store.answer()` for every key. This is what matters for the memory.

It makes one API call per document and prints no secrets. Exit code is always 0 on success: it is a
measurement, not a pass/fail gate.
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "src"))

from supersede.extract import DEFAULT_MODEL, _norm, extract_facts, load_vocabulary  # noqa: E402
from supersede.ingest import document_files, load_revisions, parse, split_document  # noqa: E402
from supersede.store import Store  # noqa: E402

RAW = ROOT / "examples" / "documents_raw"  # default folder


def score(extracted: dict[str, str], gold: dict[str, str]) -> tuple[int, int, int]:
    """(true positives, false positives, false negatives) for one document, key + normalised value."""
    tp = sum(1 for k, v in gold.items() if k in extracted and _norm(extracted[k]) == _norm(v))
    fp = len(extracted) - tp
    fn = len(gold) - tp
    return tp, fp, fn


def _prf(tp: int, fp: int, fn: int) -> tuple[float, float]:
    precision = tp / (tp + fp) if tp + fp else 1.0
    recall = tp / (tp + fn) if tp + fn else 1.0
    return precision, recall


def _store(revisions, facts_by_doc: dict[str, dict[str, str]]) -> Store:
    s = Store()
    load_revisions(s, [
        dataclasses.replace(r, facts=tuple((k.split(".", 1)[0], k.split(".", 1)[1], v)
                                           for k, v in facts_by_doc.get(r.source, {}).items()))
        for r in revisions
    ])
    return s


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--dir", default=str(RAW), help="folder with the documents, vocabulary.json and gold.json")
    args = ap.parse_args()
    folder = pathlib.Path(args.dir)
    vocab = load_vocabulary(folder / "vocabulary.json")
    gold: dict[str, dict[str, str]] = json.loads((folder / "gold.json").read_text(encoding="utf-8"))
    files = document_files(folder)
    assert {f.name for f in files} == set(gold), "gold.json and the documents do not match"

    revisions, extracted_by_doc, rejected_all = [], {}, []
    tot = [0, 0, 0]
    print(f"model: {args.model}   documents: {len(files)}   gold facts: {sum(len(g) for g in gold.values())}\n")
    print(f"{'document':<18} {'gold':>4} {'got':>4} {'TP':>3} {'FP':>3} {'FN':>3}  rejected")
    for p in files:
        text = p.read_text(encoding="utf-8")
        revisions.append(parse(text, p.name))
        _, body = split_document(text, p.name)
        result = extract_facts(body, vocab, model=args.model)
        got = {f.key: f.value for f in result.facts}
        extracted_by_doc[p.name] = got
        rejected_all += [(p.name, r) for r in result.rejected]
        tp, fp, fn = score(got, gold[p.name])
        for i, x in enumerate((tp, fp, fn)):
            tot[i] += x
        print(f"{p.name:<18} {len(gold[p.name]):>4} {len(got):>4} {tp:>3} {fp:>3} {fn:>3}  {len(result.rejected)}")
        for k, v in got.items():
            if k not in gold[p.name] or _norm(gold[p.name][k]) != _norm(v):
                print(f"    WRONG   {k} = {v!r}   (gold: {gold[p.name].get(k)!r})")
        for k, v in gold[p.name].items():
            if k not in got:
                print(f"    MISSED  {k} = {v!r}")
    precision, recall = _prf(*tot)
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    print(f"\nTOTAL  TP {tot[0]}  FP {tot[1]}  FN {tot[2]}   precision {precision:.2f}   recall {recall:.2f}   F1 {f1:.2f}")
    if rejected_all:
        print(f"\nGuard rails rejected {len(rejected_all)} model output(s):")
        for name, r in rejected_all:
            print(f"    {name}: {r.key} = {r.value!r}: {r.reason}")
    else:
        print("\nGuard rails rejected nothing.")

    gold_store, got_store = _store(revisions, gold), _store(revisions, extracted_by_doc)
    keys = sorted(vocab)

    def same_answer(a: dict, b: dict) -> bool:
        return (a.get("status"), a.get("value")) == (b.get("status"), b.get("value"))

    same = sum(same_answer(gold_store.answer(*k.split(".", 1)), got_store.answer(*k.split(".", 1))) for k in keys)
    print(f"\nEnd to end: the graph built from extracted facts gives the same answer as the gold graph for "
          f"{same} of {len(keys)} vocabulary keys today,")
    # and for every date on which a revision took effect, so supersession over the real history is checked too
    days = sorted({r.effective for r in revisions if Store._day(r.effective)})
    pairs = [(k, d) for k in keys for d in days]
    same_t = sum(same_answer(gold_store.answer(*k.split(".", 1), as_of=d), got_store.answer(*k.split(".", 1), as_of=d))
                 for k, d in pairs)
    print(f"and for {same_t} of {len(pairs)} (key, date) pairs, one date per revision effective date.")
    gold_store.close()
    got_store.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())

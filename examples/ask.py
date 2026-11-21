"""Ask the knowledge base a plain-language question from the command line. Offline.

    python examples/ask.py "How long must retained samples be kept?"
    python examples/ask.py "What sampling rule applied?" --as-of 2025-07-01
    python examples/ask.py "After how many parts do we change tools?" --db path/to/store.relate

Relate's full-text index finds the topic; the graph decides the value (supersession, authority,
ties, dates). The default store is the committed demo store, opened read-only.
"""
from __future__ import annotations

import argparse
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from supersede.store import Store  # noqa: E402

DEFAULT_DB = ROOT / "examples" / "store" / "supersede-demo.relate"


def show(r: dict) -> None:
    print(f"question : {r['question']}")
    if r["status"] in ("no_match", "no_topics"):
        print(f"result   : {r['status']}: {r['reason']}")
        return
    m, a = r["matched"], r["answer"]
    print(f"topic    : {m['subject']} / {m['predicate']}  (search score {m['score']})")
    print(f"           {m['description']}")
    print(f"status   : {a['status']}" + (f"   as of {a['as_of']}" if "as_of" in a else ""))
    if a["status"] in ("resolved", "agreed"):
        print(f"value    : {a['value']}   from {a.get('source') or ', '.join(a['sources'])}")
    if "reason" in a:
        print(f"reason   : {a['reason']}")
    for o in a.get("overruled", []):
        print(f"overruled: {o['value']!r} ({o['rev']}, authority {o['authority']})")
    for c in a.get("candidates", []):
        print(f"candidate: {c['value']!r} ({c['rev']}, authority {c['authority']})")
    for s in r.get("stale_sources", []):
        print(f"STALE    : {s['revision']} was written from {s['source']}, replaced by {', '.join(s['replaced_by'])}")
    for w in a.get("warnings", []):
        print(f"date note: {w['revision']}: {w['detail']}")
    if r["alternatives"]:
        print("also close: " + ", ".join(f"{x['subject']}/{x['predicate']}" for x in r["alternatives"]))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("question")
    ap.add_argument("--as-of", metavar="YYYY-MM-DD", help="answer for that date instead of today")
    ap.add_argument("--db", default=str(DEFAULT_DB), help="existing store (default: the committed demo store)")
    args = ap.parse_args()
    if not pathlib.Path(args.db).exists():
        ap.error(f"store not found: {args.db}")
    store = Store(args.db, read_only=True)
    try:
        show(store.ask(args.question, as_of=args.as_of))
    except ValueError as exc:
        ap.error(str(exc))
    finally:
        store.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""A scripted agent session against the Supersede MCP server, for screen recording.

Usage:
    python examples/demo_session.py                 # offline, no pauses
    python examples/demo_session.py --pause         # 1.5 s beats between steps
    python examples/demo_session.py --pause 3       # 3 s beats
    python examples/demo_session.py --llm           # also phrase one answer with a model (see below)

It loads the FICTIONAL corpus into a fresh persistent Relate store, starts the Supersede MCP
server over stdio, connects as an MCP client, and runs four steps. No network and no API calls
unless --llm is given. The store lives in a temporary directory (or at --db, which must not
exist) and the server's stderr goes to a log file that is shown only if something fails.

--llm: needs `pip install -e ".[llm]"` and ANTHROPIC_API_KEY in the environment. The key is read
only from the environment by the Anthropic SDK; it is never written anywhere.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import pathlib
import shutil
import sys
import tempfile
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "examples"))
sys.path.insert(0, str(ROOT / "eval"))

import baseline  # noqa: E402
import run_eval  # noqa: E402
from load_corpus import counts, load_docs, read_corpus  # noqa: E402
from mcp.client import Client  # noqa: E402
from mcp.client.stdio import StdioServerParameters, stdio_client  # noqa: E402
from supersede.store import Store  # noqa: E402

LLM_MODEL = "claude-haiku-5-5"

# --- terminal output (standard library only) ----------------------------------------------
if os.name == "nt":
    os.system("")  # enables ANSI escape processing in the Windows console
_COLOR = sys.stdout.isatty() and "NO_COLOR" not in os.environ
_CODES = {"bold": "1", "dim": "2", "red": "31", "green": "32", "yellow": "33", "cyan": "36"}


def c(text: str, *styles: str) -> str:
    if not _COLOR:
        return text
    return "\033[" + ";".join(_CODES[s] for s in styles) + "m" + text + "\033[0m"


class Demo:
    def __init__(self, pause: float) -> None:
        self.pause = pause

    def beat(self, factor: float = 1.0) -> None:
        if self.pause:
            sys.stdout.flush()
            time.sleep(self.pause * factor)

    def step(self, n: int, title: str) -> None:
        print()
        print(c(f"STEP {n}", "bold", "cyan") + "  " + c(title, "bold"))
        self.beat(0.6)

    def line(self, text: str = "") -> None:
        print(text)
        sys.stdout.flush()


# --- helpers ------------------------------------------------------------------------------
def doc_of(rev_id: str) -> str:
    return rev_id.rsplit("-r", 1)[0]


async def call(client: Client, tool: str, args: dict | None = None):
    r = await client.call_tool(tool, args or {})
    sc = r.structured_content
    if sc is None:  # tools that return a plain dict come back as JSON text only
        return json.loads(r.content[0].text)
    return sc["result"] if set(sc) == {"result"} else sc


def phrase_with_llm(subject: str, predicate: str, answer: dict) -> str:
    import anthropic  # optional dependency

    client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from the environment
    msg = client.messages.create(
        model=LLM_MODEL,
        max_tokens=120,
        messages=[{
            "role": "user",
            "content": (
                f"Question: what is the {predicate} for {subject}?\n"
                f"Knowledge-graph answer (JSON): {json.dumps(answer)}\n"
                "Answer the question in ONE sentence using only this JSON. Name the source "
                "and say briefly why it wins. Do not add facts."
            ),
        }],
    )
    return "".join(b.text for b in msg.content if b.type == "text").strip()


# --- the session --------------------------------------------------------------------------
async def session(demo: Demo, docs: list[dict], db: str, log, use_llm: bool) -> None:
    by_id = {d["id"]: d for d in docs}
    d_n, r_n, f_n = counts(docs)
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "supersede.mcp_server", "--db", db],
        env={**os.environ, "PYTHONPATH": str(ROOT / "src")},
    )
    async with Client(stdio_client(params, errlog=log)) as client:
        tools = [t.name for t in (await client.list_tools()).tools]
        demo.line(c("Supersede", "bold") + " - agent memory that knows which fact is in force, and why")
        demo.line(f"corpus: {d_n} documents, {r_n} revisions, {f_n} facts (all fictional)")
        demo.line(f"MCP tools ({len(tools)}): " + ", ".join(sorted(tools)[:4]) + ",")
        demo.line("  " + ", ".join(sorted(tools)[4:]))
        demo.beat(1.5)

        # 1 ---------------------------------------------------------------------------------
        subj, pred = "retained_sample", "retention_period"
        demo.step(1, "How long must retained samples be kept?")
        base = baseline.answer(docs, subj, pred)
        bdoc = by_id[doc_of(base["source"])]
        demo.line(c("  naive baseline", "yellow") + " (newest-dated fact, no graph)")
        demo.line(f"    -> {c(repr(base['value']), 'red', 'bold')}  from {base['source']} "
                  f"({bdoc['kind']}, authority {bdoc['authority']})")
        demo.beat()
        ans = await call(client, "current_answer", {"subject": subj, "predicate": pred})
        demo.line(c("  Supersede", "green") + "  current_answer")
        demo.line(f"    -> {c(repr(ans['value']), 'green', 'bold')}  from {ans['source']}")
        demo.line(f"       reason: {ans['reason']}")
        for o in ans["overruled"]:
            demo.line(c(f"       overruled: {o['value']!r} ({o['rev']}, authority {o['authority']})", "dim"))
        if use_llm:
            demo.beat()
            demo.line(c("  model phrasing", "cyan") + f" ({LLM_MODEL}, from the JSON above only)")
            demo.line("    " + phrase_with_llm(subj, pred, ans))
        demo.beat(1.5)

        # 2 ---------------------------------------------------------------------------------
        demo.step(2, "Where do current documents disagree, and who wins?")
        conflicts = await call(client, "find_contradictions")
        decided = [x for x in conflicts if x["winner"]]
        for x in decided:
            win_left = x["winner"] == x["left_fact"]
            lw, rw = ("green", "dim") if win_left else ("dim", "green")
            demo.line(f"  {x['subject']} / {x['predicate']}")
            demo.line(f"    {c(x['left_doc'] + ' (authority ' + str(x['left_authority']) + ') ' + repr(x['left_value']), lw)}"
                      f"  vs  {c(x['right_doc'] + ' (authority ' + str(x['right_authority']) + ') ' + repr(x['right_value']), rw)}")
            winner_doc = x["left_doc"] if win_left else x["right_doc"]
            demo.line(c(f"    winner: {winner_doc} (higher authority)", "green"))
            demo.beat(0.4)
        demo.line(c("  superseded revisions never appear here: their facts are history, not conflicts", "dim"))
        demo.beat(1.5)

        # 3 ---------------------------------------------------------------------------------
        demo.step(3, "What if two equal-authority sources disagree?")
        ans = await call(client, "current_answer", {"subject": "machining_cell", "predicate": "tool_change_interval"})
        demo.line(f"  current_answer(machining_cell, tool_change_interval) -> {c(ans['status'], 'yellow', 'bold')}")
        demo.line(f"    {ans['reason']}")
        for cand in ans["candidates"]:
            demo.line(f"    candidate: {cand['value']!r} from {cand['rev']} (authority {cand['authority']})")
        demo.line(c("  Supersede reports the conflict instead of guessing", "dim"))
        demo.beat(1.5)

        # 4 ---------------------------------------------------------------------------------
        demo.step(4, "How did this procedure change over time?")
        hist = await call(client, "revision_history", {"rev_id": "QP-07-r3"})
        demo.line(f"  revision_history(QP-07-r3) -> QP-07-r3 replaced " + ", then ".join(hist))
        ans = await call(client, "current_answer", {"subject": "final_inspection", "predicate": "record_retention"})
        demo.line(f"  current_answer(final_inspection, record_retention) -> {c(repr(ans['value']), 'green', 'bold')} "
                  f"from {ans['sources'][0] if 'sources' in ans else ans.get('source')}")
        demo.line(c("  r1 said 2 years and r2 said 3 years: only the newest revision counts", "dim"))
        demo.beat(1.5)


def summary_line() -> str:
    rows = run_eval.evaluate()
    n, s, b = len(rows), sum(x["ok"] for x in rows), sum(x["base_ok"] for x in rows)
    return (f"Eval on the fictional corpus ({n} questions): "
            f"{c(f'Supersede {s}/{n}', 'green', 'bold')}   vs   {c(f'naive baseline {b}/{n}', 'yellow', 'bold')}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--db", help="store path; must not exist (default: a temporary directory)")
    ap.add_argument("--pause", nargs="?", type=float, const=1.5, default=0.0, metavar="SECONDS",
                    help="pause between steps for recording (default 0; bare --pause = 1.5)")
    ap.add_argument("--llm", action="store_true", help="have a model phrase one answer (needs ANTHROPIC_API_KEY)")
    args = ap.parse_args()

    if args.llm:
        if not os.environ.get("ANTHROPIC_API_KEY"):
            sys.exit("--llm needs ANTHROPIC_API_KEY in the environment (it is never stored)")
        try:
            import anthropic  # noqa: F401
        except ImportError:
            sys.exit('--llm needs the optional SDK: pip install -e ".[llm]"')

    tmp = None
    if args.db:
        if pathlib.Path(args.db).exists():
            sys.exit(f"{args.db} already exists; pass a new path")
        db = args.db
    else:
        tmp = tempfile.mkdtemp(prefix="supersede-demo-")
        db = os.path.join(tmp, "demo.relate")
    logpath = os.path.join(tmp or tempfile.gettempdir(), "supersede-server.log")

    docs = read_corpus()
    store = Store(db)
    load_docs(store, docs)
    store.close()

    demo = Demo(args.pause)
    code = 0
    with open(logpath, "w", encoding="utf-8") as log:
        try:
            asyncio.run(session(demo, docs, db, log, args.llm))
            demo.line()
            demo.line(summary_line())
        except Exception as exc:  # show the server log only when something went wrong
            code = 1
            print(f"demo failed: {exc!r}", file=sys.stderr)
            log.flush()
            print(pathlib.Path(logpath).read_text(encoding="utf-8", errors="replace"), file=sys.stderr)
    if tmp:
        shutil.rmtree(tmp, ignore_errors=True)
    return code


if __name__ == "__main__":
    sys.exit(main())

"""A real agent (a Claude model) answering questions through the Supersede MCP server.

The model is given the server's tools and decides for itself which to call. Unlike
demo_session.py this is NOT scripted: you see the tool calls the model chose and its own answer.

Usage:
    pip install -e ".[llm]"      # the optional Anthropic SDK; set ANTHROPIC_API_KEY in your environment
    python examples/agent_demo.py                         # the built-in questions
    python examples/agent_demo.py --question "How long must retained samples be kept?"
    python examples/agent_demo.py --save docs/agent_transcript.md

It sends the questions and the tool results (fictional demo data) to the Anthropic API.
"""
from __future__ import annotations

import argparse
import asyncio
import datetime
import json
import os
import pathlib
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mcp.client import Client  # noqa: E402
from mcp.client.stdio import StdioServerParameters, stdio_client  # noqa: E402

MODEL = "claude-sonnet-5-5"
STORE = ROOT / "examples" / "store" / "supersede-demo.relate"
MAX_TURNS = 8

SYSTEM = (
    "You answer questions about a supplier's quality documents (all fictional) using the supersede tools. "
    "Prefer the `ask` tool for plain-language questions. Report the value in force, the source revision, "
    "and the reason it wins. If the status is `unresolved`, say the sources disagree and do not pick one. "
    "If a source is stale or a date warning applies, say so. Answer in at most four sentences."
)

QUESTIONS = [
    "For how long do we have to store the reference samples we keep from each lot?",
    "After how many parts do we swap the cutting tools in the machining cell?",
    "What inspection sampling rule applied in July 2025?",
    "Which form do inspectors fill in for final inspection, and can I rely on the document it comes from?",
    "Who is the plant manager?",
]


def _tools_for_api(listed) -> list[dict]:
    return [{"name": t.name, "description": t.description or "", "input_schema": t.input_schema}
            for t in listed.tools]


async def run(questions: list[str], model: str, db: str) -> list[dict]:
    import anthropic

    api = anthropic.Anthropic()
    log = open(os.path.join(tempfile.mkdtemp(prefix="agent-demo-"), "server.log"), "w")
    params = StdioServerParameters(command=sys.executable, args=["-m", "supersede.mcp_server", "--db", db],
                                   env={**os.environ, "PYTHONPATH": str(ROOT / "src")})
    transcript = []
    async with Client(stdio_client(params, errlog=log)) as mcp:
        tools = _tools_for_api(await mcp.list_tools())
        for q in questions:
            messages = [{"role": "user", "content": q}]
            calls, final = [], ""
            for _ in range(MAX_TURNS):
                resp = api.messages.create(model=model, max_tokens=1200, system=SYSTEM, tools=tools,
                                           messages=messages)
                messages.append({"role": "assistant", "content": resp.content})
                if resp.stop_reason != "tool_use":
                    final = "".join(b.text for b in resp.content if b.type == "text").strip()
                    break
                results = []
                for block in resp.content:
                    if block.type == "tool_use":
                        out = await mcp.call_tool(block.name, block.input)
                        text = out.content[0].text if out.content else ""
                        calls.append({"tool": block.name, "args": block.input, "result": text})
                        results.append({"type": "tool_result", "tool_use_id": block.id, "content": text})
                messages.append({"role": "user", "content": results})
            transcript.append({"question": q, "calls": calls, "answer": final})
    return transcript


def render(transcript: list[dict], model: str) -> str:
    lines = [
        "# A real agent using Supersede over MCP",
        "",
        f"Recorded {datetime.date.today().isoformat()} with `{model}` driving the MCP server over stdio against the",
        "committed demo store (fictional data). The model chose the tools itself. Output is verbatim; the model is",
        "not deterministic, so a re-run may word things differently.",
        "",
    ]
    for t in transcript:
        lines += [f"## {t['question']}", ""]
        for c in t["calls"]:
            args = json.dumps(c["args"], ensure_ascii=False)
            lines.append(f"* tool call: `{c['tool']}({args})`")
        lines += ["", f"**Agent:** {t['answer']}", ""]
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--question", action="append", help="ask this instead of the built-in questions (repeatable)")
    ap.add_argument("--model", default=MODEL)
    ap.add_argument("--db", default=str(STORE), help="existing store (default: the committed demo store)")
    ap.add_argument("--save", help="also write the transcript to this Markdown file")
    args = ap.parse_args()
    if not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit("needs ANTHROPIC_API_KEY in the environment (it is never stored)")
    try:
        import anthropic  # noqa: F401
    except ImportError:
        sys.exit('needs the optional SDK: pip install -e ".[llm]"')
    transcript = asyncio.run(run(args.question or QUESTIONS, args.model, args.db))
    text = render(transcript, args.model)
    print(text)
    if args.save:
        pathlib.Path(args.save).parent.mkdir(parents=True, exist_ok=True)
        pathlib.Path(args.save).write_text(text + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())

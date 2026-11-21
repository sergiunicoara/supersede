# Supersede

**Agent memory that knows which fact is currently in force, and why.**

Built for the Relate by Neo4j Hackathon on [Relate](https://relatedb.ai), the embedded graph database.

## The problem

Agents that remember facts from documents hit the same failure: a procedure gets revised, the old
revision is still in memory, and the agent happily quotes the stale one. Two documents disagree and
the agent picks whichever its retrieval returned first. Vector memory has no notion of *"this
replaced that"* or *"this source outranks that one"*.

## The idea

Model that structure explicitly as a graph, in-process, with no server:

```
(Doc {authority})-[:HAS_REV]->(Rev)-[:ASSERTS]->(Fact {subject, predicate, value})
(Rev)-[:SUPERSEDES]->(Rev)
```

* **Current** means "not superseded". It is a graph pattern, not a date comparison.
* A **contradiction** exists only between facts in *current* revisions. A fact from a superseded
  revision is history, not a conflict.
* Contradictions are **resolved by the authority** of the owning document (regulatory > procedure >
  work instruction). If authority ties, Supersede says *unresolved* instead of guessing.
* Every answer carries its **reason** and the **overruled** sources.

```
current_answer("final_inspection", "sampling")
-> {"status": "resolved", "value": "AQL 0.65", "source": "QP-07-r3",
    "reason": "QP-07 (authority 3) outranks the conflicting source(s)",
    "overruled": [{"fact": "F04", "value": "100% inspection", "rev": "WI-12-r1", ...}]}
```

## Why Relate

Relate is an embedded graph database with Cypher, so the supersession chains, the "not superseded"
pattern, and the cross-document contradiction join are each a short Cypher query, running in the
agent's own process. The store persists on disk between runs.

## Quick start

```bash
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"

python examples/seed_demo.py demo.relate     # small fictional demo knowledge base
python -m pytest -q                          # 18 tests
python examples/mcp_smoke.py demo.relate     # spawns the MCP server and calls it as an agent would
python eval/run_eval.py                      # 13 questions, Supersede vs a naive baseline
```

## Demo

A scripted agent session over a larger fictional corpus (12 documents, 19 revisions, 34 facts;
the cases are described in [examples/corpus/CASES.md](examples/corpus/CASES.md)). It starts the
MCP server over stdio, connects as an MCP client, and runs four steps: a naive baseline vs
`current_answer`, `find_contradictions`, an equal-authority conflict reported as `unresolved`,
and `revision_history`. It ends with the eval scores. Fully offline.

```bash
python examples/demo_session.py            # add --pause to slow it down for recording
```

Optional: `pip install -e ".[llm]"`, set `ANTHROPIC_API_KEY` in your environment, and add `--llm`
to have a model phrase the step-1 answer in one sentence from `current_answer`'s JSON. The key is
read from the environment only and is never stored.

### Use it from an MCP client

```json
{
  "mcpServers": {
    "supersede": {
      "command": "python",
      "args": ["-m", "supersede.mcp_server", "--db", "demo.relate"],
      "env": { "PYTHONPATH": "src" }
    }
  }
}
```

Tools: `current_answer`, `find_contradictions`, `current_revisions`, `revision_history`.

Relate mode used: **persistent on-disk store** (`--db path`; Relate keeps it as a directory), with
`:memory:` as the default for tests. Memory-only would lose the revision history between runs,
which is the point of the project.

## Design notes

* **Thread affinity.** Relate connections are thread-affine (DB-API `threadsafety = 1`), and an MCP
  server calls tools from worker threads. `Store` runs all database work on one dedicated thread;
  a regression test covers it.
* **Stale facts.** An early version of the contradiction query compared facts across *all*
  revisions and flagged superseded ones. The current query excludes them, and a test pins that
  behavior.

## Disclosures (per the contest rules)

* **Started:** 21 November 2026, inside the contest period. No pre-existing project is submitted.
* **Reused code:** none copied. The *concepts* (document authority hierarchy, `SUPERSEDES` chains,
  contradiction detection) come from the author's earlier GraphRAG work; this implementation was
  written from scratch for Relate.
* **Data:** all demo data is fictional and written for this repo. No client or third-party documents.
* **AI tools:** the code, tests and this README were developed with substantial assistance from
  Claude (Anthropic). The author directed the design and is responsible for the result.
* **Third-party:** Relate (`relate-db` 1.2.0, Apache-2.0) and the MCP Python SDK. Dev only:
  pytest and PyYAML. Optional (`--llm` in the demo only): the Anthropic Python SDK.

## License

MIT. See [LICENSE](LICENSE).

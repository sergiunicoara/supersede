# Supersede

*Agent memory that knows which fact is currently in force, and why.*

Repository: https://github.com/sergiunicoara/supersede (MIT). Built on Relate by Neo4j.

## The problem

Agents that remember facts from documents fail in a predictable way. A procedure is revised, but the old
revision is still in memory, so the agent quotes the stale one. Two documents disagree, and the agent returns
whichever its retrieval ranked first. Vector memory has no notion of "this replaced that" or "this source outranks
that one".

**Who it is for:** quality and compliance teams, and the agents that work over their revised procedures, customer
requirements, work instructions and shift notes, where quoting a superseded value, or picking the wrong one of two
conflicting documents, has real consequences.

## What it does

Supersede stores documents, their revisions and the facts each revision asserts as a graph, and answers with the
value that is *in force*, plus the reason.

```
Q: How long must retained samples be kept?
naive baseline (newest fact wins):  3 years    (a night-shift note)
Supersede:                          10 years   from the customer requirement CSR-VEL-01-r2
  reason:    CSR-VEL-01 (authority 4) outranks the conflicting source(s)
  overruled: 5 years (QP-15-r1, authority 3), 3 years (SN-0914-r1, authority 1)
```

* **Current** means "not superseded": a graph pattern, not a date comparison. A fact in a superseded revision is
  history, never a conflict.
* **Authority resolves conflicts** (customer requirement > controlled procedure > work instruction > shift note).
  Equal authority is reported as `unresolved`, never guessed.
* **Plain-language questions:** hybrid retrieval (Relate's full-text and vector indexes) finds the topic, then the graph decides the value.
* **Time:** what was in force on a past date. Missing, mistyped or out-of-order dates are reported, never guessed.
  A web page draws every revision on a timeline and a **date slider** shows the winning value change as you drag it
  (pictures of it are in the README).
* **Lineage:** a revision can record the revision of another document it was written from, so Supersede flags a
  current document that rests on a source that has since been replaced.
* **MCP server** with eight read-only tools, so any MCP-capable agent can use it: `ask`, `current_answer`,
  `answer_as_of`, `find_contradictions`, `current_revisions`, `revision_history`, `stale_derivations`,
  `date_warnings`.

## How Relate is used

Everything runs in the agent's own process, with no server, on **Relate in directory mode** (a persistent store that
survives restarts and can be inspected; a small one is committed in the repo). Revision history is the point of the
project, so memory-only mode would defeat it.

```
(Doc {authority})-[:HAS_REV]->(Rev)-[:ASSERTS]->(Fact {subject, predicate, value})
(Rev)-[:SUPERSEDES]->(Rev)        // within a document: newer replaces older
(Rev)-[:DERIVED_FROM]->(Rev)      // across documents: written from that revision
(Topic {subject, predicate, description, embedding})   // searched by Relate's full-text and vector indexes
```

Each behaviour is a short Cypher query, for example the contradiction join that only looks at current revisions,
and the retrieval step feeding the graph:

```cypher
MATCH (da:Doc)-[:HAS_REV]->(ra:Rev)-[:ASSERTS]->(a:Fact)
MATCH (db:Doc)-[:HAS_REV]->(rb:Rev)-[:ASSERTS]->(b:Fact)
WHERE a.subject = b.subject AND a.predicate = b.predicate AND a.value <> b.value AND a.fid < b.fid
  AND NOT (:Rev)-[:SUPERSEDES]->(ra) AND NOT (:Rev)-[:SUPERSEDES]->(rb)

MATCH (t:Topic) SEARCH t IN (FULLTEXT INDEX topic_text FOR $q LIMIT 10) SCORE AS score
MATCH (t:Topic) SEARCH t IN (VECTOR INDEX topic_vec FOR $v LIMIT 10) SCORE AS score
```

**Relate capabilities used:** the embedded Python DB-API (`$name` parameters, commit, close); a persistent directory
store, also opened read-only; `MERGE`; `NOT (...)` pattern predicates; unbounded variable-length paths
(`[:SUPERSEDES*1..]`, `[:DERIVED_FROM*1..]`, `*0..` for cycle checks); multi-`MATCH` joins; a **full-text index**
and a **vector index** (`CREATE FULLTEXT INDEX`, `CREATE VECTOR INDEX`, `SEARCH ... SCORE AS`) that persist in the
store and work on a read-only open, fused by reciprocal rank in Python by default; Relate's own `COMBINE` (a preview feature) is an opt-in and measured slightly worse here. Relate does
not compute embeddings; Supersede uses a small dependency-free hashing embedder (word forms and typos, not true
synonyms). **Not used:** Relate's own MCP
server, the CLI, Bolt or HTTP, WebAssembly. Supersede ships its own MCP server with domain tools instead.

## How I built it

I probed which Cypher features Relate 1.2.0 supports before designing around them (`examples/probe_cypher.py`).
Relate connections are thread-affine but an MCP server calls tools from worker threads, so `Store` runs all database
work on one dedicated thread. Writes are strict: unknown ids, a reused fact id, a non-integer authority or a cycle
raise instead of silently doing nothing. Documents load from annotated Markdown, and an optional extraction tool
proposes facts from plain prose, with guard rails (a fixed vocabulary, a verbatim quote that must appear in the
text, rejections listed and never written, and a human-review copy). The suite has 192 tests (188 run on a plain install; the rest need an API key or the optional model), and CI runs on
Linux, macOS and Windows with Python 3.10 to 3.13.

## Does it work? The numbers, and how to read them

| Test | Supersede | Baseline |
|---|---|---|
| 19 revision questions (fictional corpus, designed cases) | **19/19** | 9/19 (newest date wins) |
| 23 plain-language questions, correct end to end | **23/23** | 13/23 (same search, newest date) |
| 13 "what was in force on this date" questions | **13/13** | 11/13 (newest fact before the date) |
| 3 cross-document lineage checks | **3/3** | n/a (baselines keep no derivation structure) |
| Extraction on real regulation text, 29 gold facts, three runs | **27/29**, no invented fact | first, blind run on the new keys: 24/27 |

Read these as demonstrations of behaviour, not benchmarks: the cases are mine, several numbers come from a run
*after* a fix informed by an earlier run (each is labelled in `docs/EVIDENCE.md`, with the blind result next to
it), and the baselines are deliberately simple. Two baseline misses are by construction (no baseline can report a
disagreement), and the date cases were designed to separate dates from supersession.

## Real-world evidence, and its limits

The demo corpus is fictional, so I also tested on **real text**: US federal regulations from the public eCFR,
including FDA's device quality regulation (21 CFR Part 820) before and after its 2026 rewrite. A record-retention
requirement ("no less than 2 years") that the 2016 text states is no longer stated in the 2026 text, so Supersede
answers `2 years` for a date before 2026 and `unknown` today. I also tested a **real authority hierarchy**: FDA's
non-binding 2016 guidance still cites a regulation section removed in 2026, so Supersede answers with the regulation,
lists the guidance as overruled, answers with the guidance for earlier dates, and flags the guidance as written
from replaced text.

**Limits, stated plainly:** this is 16 documents in 7 chains that I chose; the hierarchy is statute-style
(regulation over guidance), not a plant's own tiers, so company documents, shift notes and emails are untested on real
data; values are compared as exact strings (`2 years` and `two years` count as different, though authority settles it
here); and a revision replaces the whole previous one, so a requirement a new revision stops stating is treated as no
longer in force. Everything, with the blind runs, is in `docs/EVIDENCE.md`.

## What I learned

* **A baseline keeps you honest.** My first eval had "newest date" tied with "follow `SUPERSEDES`", because every
  newer revision was also newer by date. Real metadata is messier, so I added missing, mistyped and irrelevant dates.
* **Bad input must fail loudly.** Auditing my own code found a reused fact id silently overwriting another
  revision's fact, a history query that stopped after 20 hops, and a conflict inside one revision going unreported.
  Each is fixed and tested.
* **Don't guess on ties.** When equal-authority sources disagree, the honest answer is `unresolved`.
* **Real APIs find what fakes cannot.** The extraction model rejected a forced tool choice that my fake-client tests
  never exercised.

## What's next

Value normalisation (`2 years` = `two years`); extracting revision links from the text itself, not only facts;
company-internal documents in place of public regulations; per-subject authority rules; and making the optional trained embedding model (already available as an extra) the default where it can be installed.

## Try it

```bash
python -m venv .venv && . .venv/bin/activate    # Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -e ".[dev]"
python examples/demo_session.py                  # a naive baseline vs Supersede, offline
python examples/ask.py "How long must retained samples be kept?"
python examples/ask.py "What sampling rule applied?" --as-of 2025-07-01
python web/app.py                                # then open http://127.0.0.1:7860 and drag the date slider
# or, with nothing to install: https://supersede-demo.onrender.com  (free instance; allow about a minute to wake)
```

Requires Python 3.10 or later; nothing needs the network after `pip install`. The persistent Relate store is
committed at `examples/store/supersede-demo.relate/` (directory mode; open it with
`relate.connect(path, read_only=True)`). A recorded run of a real Claude agent using the MCP server is in
`docs/agent_transcript.md`.

## Built with

Relate (`relate-db` 1.2.0, Apache-2.0), Python, the MCP Python SDK, pytest and PyYAML (dev). Optional: the Anthropic
Python SDK, for the extraction tool, the real-agent demo and the demo's `--llm` flag (all off by default; the default
path is offline). Claude (Anthropic) was also used as a development assistant, described next.

## Disclosures

* **Started:** 21 November 2026, inside the contest period. No pre-existing project is submitted.
* **Reused code:** none copied. The *concepts* (document authority hierarchy, `SUPERSEDES` chains, contradiction
  detection) come from my earlier GraphRAG work; this implementation was written from scratch for Relate.
* **Data:** the corpus and demo data are fictional and written for this repo. `examples/real/` contains text of US
  federal regulations from the eCFR and an excerpt of one FDA guidance document; these are works of the US government
  in the public domain, and every file states its source and version date. No client documents, and no
  copyrighted third-party text (ISO 13485, which the 2026 regulation incorporates by reference, is not included).
* **AI tools:** Claude (Anthropic), used through Claude Code, helped throughout: the code, tests, the fictional corpus
  and eval questions, the eval and baselines, the demo scripts and the screen capture of the demo, a repo audit, and
  the README, submission text and video script. I directed the design and am responsible for the result. Separately,
  the optional extraction tool, the real-agent demo and the demo's `--llm` flag call a Claude model at run time and send
  text to the Anthropic API.
* **Third-party:** Relate (Apache-2.0) and the MCP Python SDK. Dev only: pytest and PyYAML. Optional: the Anthropic
  Python SDK and API.

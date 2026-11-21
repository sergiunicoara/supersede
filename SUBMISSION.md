# Devpost submission draft: Supersede

## 1. Project name and tagline

**Supersede**

*Agent memory that knows which fact is currently in force, and why.*

## 2. Inspiration

Agents that remember facts from documents hit the same failure: a procedure gets revised, the old
revision is still in memory, and the agent quotes the stale one. When two documents disagree, the
agent picks whichever its retrieval returned first. Vector memory has no notion of "this replaced
that" or "this source outranks that one". I had worked on these ideas before in GraphRAG work
(document authority, supersession chains, contradiction detection), and Relate's embedded graph
database was a chance to rebuild them from scratch as a small, in-process memory layer that any
agent can query.

**Who it is for.** Quality and compliance teams, and the agents that work over their revised
procedures, customer requirements, work instructions and shift notes, where quoting a superseded
value or picking the wrong one of two conflicting documents has real consequences. The demo uses
an invented automotive-quality corpus for that reason.

## 3. What it does

Supersede stores documents, their revisions, and the facts each revision asserts as a graph. A
revision is *current* if no other revision supersedes it. A *contradiction* only exists between
facts in current revisions: a fact from a superseded revision is history, not a conflict. When
current facts disagree, Supersede resolves the conflict by the authority of the owning document:
customer-specific requirement (4) > controlled procedure (3) > work instruction (2) > shift note or
email (1). If authority ties, it reports the answer as *unresolved* instead of guessing. Every
answer carries its reason and the sources it overruled.

For example, on the demo corpus (fictional quality documents), asking how long retained samples
must be kept returns `10 years` from the customer requirement `CSR-VEL-01-r2`, with the reason
"CSR-VEL-01 (authority 4) outranks the conflicting source(s)" and the two overruled facts
(`5 years` from `QP-15-r1`, `3 years` from a night-shift note, `SN-0914-r1`).

**What is different from plain vector memory.** A vector store ranks text by similarity and has no
idea which passage replaced which or which source outranks which. Supersede makes that structure
part of the graph: revision chains (`SUPERSEDES`) and document authority are edges and properties
you can query; contradictions are only looked for between current revisions, so old values do not
raise false alarms; and when equal-authority sources disagree it says `unresolved` rather than
returning one of them.

Supersede runs as an MCP server, so any MCP-capable agent can use it. The four tools:

| Tool | What it returns |
|---|---|
| `current_answer(subject, predicate)` | The value in force, with status (`agreed`, `resolved`, `unresolved`, or `unknown`), the reason, and any overruled sources |
| `find_contradictions()` | All conflicts between facts in current revisions, with the authority-based winner (or `null` on a tie) |
| `current_revisions()` | Revision ids that have not been superseded |
| `revision_history(rev_id)` | The revisions that `rev_id` replaced, nearest first |

## 4. How Relate is used

**Graph model**

```
(Doc {authority})-[:HAS_REV]->(Rev)-[:ASSERTS]->(Fact {subject, predicate, value})
(Rev)-[:SUPERSEDES]->(Rev)
```

**Key Cypher patterns** (all from `src/supersede/store.py`)

*Current = not superseded.* In plain terms: a revision is in force if no newer revision points at it
with `SUPERSEDES`. "Current" is a graph pattern, not a date comparison:

```cypher
MATCH (r:Rev) WHERE NOT (:Rev)-[:SUPERSEDES]->(r) RETURN r.id AS id ORDER BY id
```

*Contradiction join restricted to current revisions.* In plain terms: find two facts about the same
thing that give different values, but only if both come from revisions that are still in force, so
old values never count as conflicts. Each pair is reported once:

```cypher
MATCH (da:Doc)-[:HAS_REV]->(ra:Rev)-[:ASSERTS]->(a:Fact)
MATCH (db:Doc)-[:HAS_REV]->(rb:Rev)-[:ASSERTS]->(b:Fact)
WHERE a.subject = b.subject AND a.predicate = b.predicate
  AND a.value <> b.value AND a.fid < b.fid
  AND NOT (:Rev)-[:SUPERSEDES]->(ra) AND NOT (:Rev)-[:SUPERSEDES]->(rb)
RETURN ...
```

*Variable-length history.* In plain terms: follow `SUPERSEDES` links backwards from a revision, one
hop or many, however long the chain, and list everything it replaced, nearest first:

```cypher
MATCH p=(n:Rev {id: $id})-[:SUPERSEDES*1..]->(o:Rev) WHERE o.id <> n.id
RETURN o.id AS id, length(p) AS hops ORDER BY hops
```

The same three-hop traversal `Doc -> Rev -> Fact` also drives `current_answer`, carrying each
fact's document authority so the winner can be explained.

**Persistent store mode.** The server uses Relate's on-disk store (`--db path`; Relate keeps it as
a directory), with `:memory:` as the default for tests. Memory-only would lose the revision history
between runs, and history is the whole point of the project. A test (`test_persists_across_reopen`)
closes the store, reopens it, and checks the data is still there.

## 5. How I built it

The first step was `examples/probe_cypher.py`, which runs a dozen probes against Relate 1.2.0
(NOT-pattern, variable-length paths, self-join, parameters, `collect()`, `OPTIONAL MATCH`, `EXISTS`
subqueries, `MERGE`, and others) and prints PASS/FAIL for each, so the design rests on the real
Cypher support surface rather than assumed Neo4j parity.

The store (`Store`) wraps Relate with a small write API (add document, add revision, supersede,
assert fact) and the read queries above. The MCP server exposes the four tools using the MCP Python
SDK; every tool only reads, so it opens an existing store read-only and refuses a path that does
not exist. `examples/mcp_smoke.py` spawns the server over stdio and calls it the way an agent would.
Documents can be loaded from annotated Markdown (`python -m supersede.ingest`): one file per
revision, a small header, and facts marked inline with `{{subject.predicate = value}}`.

To test it beyond a handful of facts I wrote a fictional automotive-quality corpus (15 documents,
25 revisions, 46 facts; `examples/corpus/`) with nine deliberate cases (`CASES.md`), a 19-question
eval (`eval/run_eval.py`), a naive baseline and two ablations for comparison (`eval/baseline.py`), and a scripted
agent session that drives the MCP server end to end (`examples/demo_session.py`), which the demo
video follows.

**The thread-affinity issue.** Relate connections are thread-affine (DB-API `threadsafety = 1`),
but an MCP server dispatches tool calls on worker threads, so a connection created on one thread
cannot be used from another. The fix: `Store` owns a single-thread executor and runs *all* database
work, including opening the connection, on that one thread. Every public method submits its work to
the executor and waits for the result, so one connection stays valid for both file and in-memory
databases no matter which thread calls. A regression test (`test_usable_from_other_threads`)
queries the store from a separate thread.

## 6. Challenges and what I learned

* **Stale facts looked like conflicts.** An early version of the contradiction query compared facts
  across *all* revisions and flagged superseded ones. Restricting the join to current revisions
  fixed it, and a test pins the behavior (a fact from a superseded revision must not produce a
  contradiction).
* **Thread affinity** (section 5): an MCP server calls tools from worker threads, which a
  thread-affine connection does not allow. Funnelling everything through one thread was the
  simplest fix I found.
* **Don't guess on ties.** When equal-authority sources disagree, the honest answer is
  `unresolved`, with the candidates listed. This is covered by a test.
* **Probe first.** `examples/probe_cypher.py` checks the Cypher features the design needs against
  Relate; all twelve probes pass, so the queries above rest on tested support, not assumed Neo4j
  parity.
* **Bad input must fail loudly.** An audit of my own code found that a reused fact id silently
  overwrote another revision's fact, a missing id was a silent no-op, a cycle in `SUPERSEDES` left
  nothing current, and the history query stopped after 20 hops. Writes now raise `ValueError` for
  all of these, history follows the whole chain, and a conflict inside a single revision is now
  reported. Each fix has a test.
* **A baseline keeps you honest.** My first eval had a newest-date baseline at 9 of 13, and an
  ablation showed that following `SUPERSEDES` added nothing over dates there, because every newer
  revision was also newer by date. Real metadata is messier, so I added cases with missing, wrong
  or irrelevant dates and re-ran everything. The results below say exactly where each part of the
  graph helps.

## 7. Results

Measured with `python eval/run_eval.py` on the fictional corpus (15 documents, 25 revisions,
46 facts) and 19 questions, two or three per case (`examples/corpus/CASES.md`). Supersede answers
through `Store.answer()`. The **naive baseline** (`eval/baseline.py`) ignores `SUPERSEDES` and
authority and returns the fact from the most recent effective date across all documents. Two
**ablations** each keep one part of the graph: *supersession-aware* (skips superseded revisions,
ignores authority) and *authority-aware* (uses document authority, ignores `SUPERSEDES`).

```
case          questions  Supersede  newest date  supersession-aware  authority-aware
stale                 2      2/2          2/2                2/2               2/2
authority             3      3/3          1/3                1/3               3/3
unresolved            2      2/2          0/2                0/2               0/2
agreed                2      2/2          2/2                2/2               2/2
unknown               2      2/2          2/2                2/2               2/2
chain                 2      2/2          2/2                2/2               2/2
missing_date          2      2/2          0/2                2/2               0/2
date_error            2      2/2          0/2                2/2               0/2
withdrawn             2      2/2          0/2                2/2               0/2
TOTAL                19     19/19         9/19              15/19             11/19
```

**Supersede: 19/19. Baseline (newest effective date, no graph): 9/19. Ablations: following
`SUPERSEDES` only 15/19; using authority only 11/19.**

How to read it:

* A Supersede answer is correct only if the status (`agreed`, `resolved`, `unresolved`, `unknown`),
  the value and the source revision all match. The baseline is scored on the value only, which is
  generous to it.
* The first six case types are the original set: there, a newer revision is always newer by date
  too, so newest-date and following `SUPERSEDES` give the same answers, and the baseline gets the
  `stale`, `agreed`, `unknown` and `chain` questions right.
* The three new case types are about metadata that is missing, wrong or irrelevant: a revision with
  a blank effective date (`missing_date`), an old revision whose date was mistyped as 2052
  (`date_error`), and a newer revision that drops a requirement (`withdrawn`). Date-based methods
  fail all six questions; following `SUPERSEDES` answers all six. **I designed these cases to
  separate the two, and I do not know how often such metadata problems occur in real corpora.**
* The baseline's two `authority` errors are a lower-authority source that is newer than the
  controlling one (a night-shift note beats a customer requirement on retention period; a work
  instruction beats a customer requirement on paint film thickness). Authority alone fixes them.
* Its two `unresolved` misses are by construction: no baseline can report a disagreement, so it
  always guesses one value. Only Supersede reports it.
* Each part of the graph earns something different: following `SUPERSEDES` is worth 6 of the 19
  questions beyond dates, authority is worth 2, and tie detection is worth 2. Supersede is the only
  one that answers all of them.
* `withdrawn` rests on a modelling choice: a revision replaces the whole previous one, so a fact it
  does not restate is not in force. Supersede cannot tell a deliberately withdrawn requirement
  from one the author forgot to carry over.
* The suite has 52 tests, including edge cases (cycles, reused fact ids, missing ids, a 120-revision
  chain, a conflict inside one revision), the Markdown ingestion, a check that the MCP server leaves
  a store byte-identical, and one that runs the demo end to end over MCP.

**Caveat:** all data is fictional and small, written for this repo. Real documents are messier:
wording differs between documents, supersession is not always recorded, and authority is not always
a clean ranking. These results show the behavior on designed cases, not performance on real
corpora.

## 8. What's next

These are plans, not features in the repo today.

* **Automatic extraction.** Ingestion today reads facts that an author has marked inline in
  Markdown; it does not extract facts or revision links from unannotated text. Doing that reliably
  is the next step.
* **Value normalisation.** Contradictions compare values as exact strings, so `100%` and
  `100% inspection` count as different. Normalising values (or adding a similarity check) would cut
  false conflicts.
* **Richer authority.** Authority is currently one integer per document. Per-subject or
  effective-date-aware rules would handle cases where a lower-ranked source is correctly more
  specific.

## 9. Built with

* [Relate](https://relatedb.ai) (`relate-db` 1.2.0, embedded graph database, Cypher)
* Python (3.10+)
* MCP Python SDK (Model Context Protocol server over stdio)
* pytest and PyYAML (tests, corpus and eval data)
* Anthropic Python SDK, optional and only for the demo's `--llm` flag (off by default; the demo
  runs fully offline)
* Claude (Anthropic), used as a development assistant (see Disclosures)

**Relate capabilities used:** the embedded Python DB-API (`relate.connect`, `$name` parameters,
commit, close); a persistent directory store, also opened `read_only=True` (the committed demo
store); `MERGE` upserts; `NOT (...)` pattern predicates; unbounded variable-length paths
(`[:SUPERSEDES*1..]`, and `*0..` for the cycle check) with `length(p)`; multi-`MATCH` joins;
`ORDER BY` and `count()`. **Not used:** vector or full-text search, Relate's own MCP server, the
CLI, Bolt or HTTP, WebAssembly. Supersede exposes its own MCP server with four domain tools
instead.

**Third-party tools:** the MCP Python SDK, PyYAML and pytest; optionally the Anthropic Python SDK.
**AI tools:** Claude (Anthropic) through Claude Code, as described in Disclosures.

## 10. Disclosures

* **Started:** 21 November 2026, inside the contest period. No pre-existing project is submitted.
* **Reused code:** none copied. The *concepts* (document authority hierarchy, `SUPERSEDES` chains,
  contradiction detection) come from my earlier GraphRAG work; this implementation was written from
  scratch for Relate.
* **Data:** all demo data is fictional and written for this repo. No client or third-party
  documents.
* **AI tools:** Claude (Anthropic), used through Claude Code, helped throughout: the code, tests,
  the fictional corpus and eval questions, the eval and baselines, the demo scripts and the screen
  capture of the demo, a repo audit, and the README, submission text and video script. I directed
  the design and am responsible for the result.
* **Third-party:** Relate (`relate-db` 1.2.0, Apache-2.0) and the MCP Python SDK. Dev only: pytest
  and PyYAML. Optional (`--llm` in the demo only): the Anthropic Python SDK.

# Devpost submission draft: Supersede

> Draft for pasting into Devpost. Items marked **[CONFIRM]** are your decisions. This file also ends
> with a judging-criteria note that is for you, not for Devpost: delete it before pasting.

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
MATCH (da:Doc)-[:HAS_REV]->(ra:Rev)-[:ASSERTS]->(a:Fact),
      (db:Doc)-[:HAS_REV]->(rb:Rev)-[:ASSERTS]->(b:Fact)
WHERE a.subject = b.subject AND a.predicate = b.predicate
  AND a.value <> b.value AND a.fid < b.fid
  AND NOT (:Rev)-[:SUPERSEDES]->(ra) AND NOT (:Rev)-[:SUPERSEDES]->(rb)
RETURN ...
```

*Variable-length history.* In plain terms: follow `SUPERSEDES` links backwards from a revision, one
hop or many (up to 20), and list everything it replaced, nearest first:

```cypher
MATCH p=(n:Rev {id: $id})-[:SUPERSEDES*1..20]->(o:Rev)
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
SDK. `examples/mcp_smoke.py` spawns the server over stdio and calls it the way an agent would.

To test it beyond a handful of facts I wrote a fictional automotive-quality corpus (12 documents,
19 revisions, 34 facts; `examples/corpus/`) with six deliberate cases (`CASES.md`), a 13-question
eval (`eval/run_eval.py`), a naive baseline for comparison (`eval/baseline.py`), and a scripted
agent session that drives the MCP server end to end (`examples/demo_session.py`), which is what the
demo video shows.

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
* **A baseline keeps you honest.** The naive baseline gets 9 of 13 questions right, including all
  the stale-revision ones, because newest-wins is often correct. The graph earns its keep where
  authority and disagreement matter, and the results below say exactly where.

## 7. Results

Measured with `python eval/run_eval.py` on the fictional corpus (12 documents, 19 revisions,
34 facts) and 13 questions, one or more per case (`examples/corpus/CASES.md`). Supersede answers
through `Store.answer()`. The **naive baseline** (`eval/baseline.py`) ignores `SUPERSEDES` and
authority and returns the fact from the most recent effective date across all documents.

```
case        questions  Supersede  Baseline
stale               2      2/2       2/2
authority           3      3/3       1/3
unresolved          2      2/2       0/2
agreed              2      2/2       2/2
unknown             2      2/2       2/2
chain               2      2/2       2/2
TOTAL              13     13/13      9/13
```

**Supersede: 13/13. Baseline (newest effective date, no graph): 9/13.**

How to read it:

* A Supersede answer is correct only if the status (`agreed`, `resolved`, `unresolved`, `unknown`),
  the value and the source revision all match. The baseline is scored on the value only, which is
  generous to it.
* The baseline's two real errors are in `authority`: a lower-authority source is newer than the
  controlling one (a night-shift note beats a customer requirement on retention period; a work
  instruction beats a customer requirement on paint film thickness).
* Its two `unresolved` misses are by construction: it cannot report a disagreement, so it always
  guesses one value.
* It gets the `stale`, `agreed`, `unknown` and `chain` questions right. When the newest revision is
  also the newest dated source, ignoring the graph costs nothing. The questions were not chosen to
  hide that.
* The suite has 18 tests, including one that runs the demo end to end over MCP.

**Caveat:** all data is fictional and small, written for this repo. Real documents are messier:
wording differs between documents, supersession is not always recorded, and authority is not always
a clean ranking. These results show the behavior on designed cases, not performance on real
corpora.

## 8. What's next

These are plans, not features in the repo today. **[CONFIRM]** that you want to commit to them.

* **Ingestion.** Today facts and `SUPERSEDES` links are written through the `Store` API; there is no
  document parsing. Next would be extracting facts and revision links from documents.
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

## 10. Disclosures

* **Started:** 21 November 2026, inside the contest period. No pre-existing project is submitted.
* **Reused code:** none copied. The *concepts* (document authority hierarchy, `SUPERSEDES` chains,
  contradiction detection) come from my earlier GraphRAG work; this implementation was written from
  scratch for Relate.
* **Data:** all demo data is fictional and written for this repo. No client or third-party
  documents.
* **AI tools:** the code, tests and documentation were developed with substantial assistance from
  Claude (Anthropic). I directed the design and am responsible for the result.
* **Third-party:** Relate (`relate-db` 1.2.0, Apache-2.0) and the MCP Python SDK. Dev only: pytest
  and PyYAML. Optional (`--llm` in the demo only): the Anthropic Python SDK.

---

## Judging-criteria note (for you; delete before pasting)

| Criterion | Supported by | Gap |
|---|---|---|
| **Creativity** | Section 3, "What is different from plain vector memory": revision chains and authority as graph structure, conflicts only between current revisions, honest `unresolved` | Argued against vector memory only, as requested; nothing is claimed about other entries |
| **Usefulness** | Section 2, "Who it is for": quality and compliance teams and agents over revised procedures; Section 3 worked example | Evidence is on designed fictional cases. There is no ingestion (Section 8), so facts and links are entered through the `Store` API today, not extracted from documents |
| **Completeness** | Sections 3, 5, 7: four working MCP tools, persistent store, corpus, 13-question eval, baseline, scripted demo, 18 tests | The video is a script, not a recorded video; the recording is still to do |
| **Clarity** | Sections 3, 4, 7: plain-language sentence before each query, the measured table, the worked example | Section 7 is the densest part; the baseline scoring notes could be cut to one line if space is tight |
| **Effective use of connected context** | Sections 4, 7: answers come from traversing Doc -> Rev -> Fact and the `SUPERSEDES` chain with authority; the contradiction join depends on graph structure; persistent mode keeps the history; 13/13 vs 9/13 | The baseline is newest-date-wins, not a vector-retrieval baseline, so Section 7 does not show a vector-search comparison. Say "naive baseline", as written, not "vector baseline" |

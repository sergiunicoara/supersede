# Devpost submission draft: Supersede

> Draft for pasting into Devpost. Items marked **[NEEDS DATA]** or **[CONFIRM]** are things the repo
> cannot back; resolve or delete them before submitting. This file also ends with a judging-criteria
> note that is for you, not for Devpost: delete it before pasting.

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

## 3. What it does

Supersede stores documents, their revisions, and the facts each revision asserts as a graph. A
revision is *current* if no other revision supersedes it. A *contradiction* only exists between
facts in current revisions: a fact from a superseded revision is history, not a conflict. When
current facts disagree, Supersede resolves the conflict by the authority of the owning document
(for example customer requirements > controlled procedure > informal work instruction). If
authority ties, it reports the answer as *unresolved* instead of guessing. Every answer carries its
reason and the sources it overruled.

For example, on the demo knowledge base (fictional quality procedures),
`current_answer("final_inspection", "sampling")` returns `AQL 0.65` from `QP-07-r3`, with the reason
"QP-07 (authority 3) outranks the conflicting source(s)" and the overruled work-instruction fact
(`100% inspection`, `WI-12-r1`).

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

*Current = not superseded.* "Current" is a graph pattern, not a date comparison:

```cypher
MATCH (r:Rev) WHERE NOT (:Rev)-[:SUPERSEDES]->(r) RETURN r.id AS id ORDER BY id
```

*Contradiction join restricted to current revisions.* Two facts with the same subject and predicate
but different values, both owned by non-superseded revisions, and each pair reported once:

```cypher
MATCH (da:Doc)-[:HAS_REV]->(ra:Rev)-[:ASSERTS]->(a:Fact),
      (db:Doc)-[:HAS_REV]->(rb:Rev)-[:ASSERTS]->(b:Fact)
WHERE a.subject = b.subject AND a.predicate = b.predicate
  AND a.value <> b.value AND a.fid < b.fid
  AND NOT (:Rev)-[:SUPERSEDES]->(ra) AND NOT (:Rev)-[:SUPERSEDES]->(rb)
RETURN ...
```

*Variable-length history.* Everything a revision replaced, nearest first:

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
* **Thread affinity** (section 5) only shows up once the server runs under real MCP dispatch, not in
  single-threaded tests. Funnelling everything through one thread was the simplest correct fix.
* **Don't guess on ties.** When equal-authority sources disagree, the honest answer is
  `unresolved`, with the candidates listed. This is covered by a test.
* **Probe first.** Checking the Cypher surface up front avoided designing around features the
  database might not support.

## 7. Results

**[NEEDS DATA]** I have no measured scores against a naive baseline in the repository. If you ran an
evaluation, paste the numbers here with the baseline's definition and the data size. Do not submit
this section until it is filled or removed. What the repository can support today:

* **Tests:** 9 tests pass (`python -m pytest -q`). They cover: current revisions exclude superseded
  ones; history lists replaced revisions; a stale fact is not a contradiction; authority resolves a
  contradiction; answers explain why; equal-authority conflicts are reported, not hidden; unknown
  when nothing is asserted; persistence across reopen; use from another thread.
* **End to end:** `examples/mcp_smoke.py` lists the four tools and gets a resolved answer for
  `final_inspection / sampling` from a persisted store.
* **Illustration, not a benchmark:** in the demo knowledge base, four facts across four revisions
  state a sampling rule for `final_inspection` (`100% inspection`, `AQL 1.0`, `AQL 0.65`,
  `100% inspection`). Two of those revisions are current; Supersede returns the single value in
  force (`AQL 0.65`) and the one it overruled. A retrieval that does not model supersession has
  four candidates to choose from.

**Caveat:** all data is fictional and small, written for this repo. Real documents are messier:
wording differs between documents, supersession is not always recorded, and authority is not always
a clean ranking. These results should not be read as performance on real corpora.

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
* pytest
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
* **Third-party:** Relate (`relate-db` 1.2.0, Apache-2.0) and the MCP Python SDK.

---

## Judging-criteria note (for you; delete before pasting)

| Criterion | Supported by | Gap |
|---|---|---|
| **Creativity** | Sections 2, 3: supersession and authority as first-class graph structure, "unresolved" instead of guessing | Differentiation from other agent-memory entries isn't argued; one sentence on that would help |
| **Usefulness** | Sections 2, 3: stale and conflicting facts are a real agent failure; works from any MCP client | No real-document evidence, no ingestion (Section 8), and the quality-procedure domain is only implied; say who would use it |
| **Completeness** | Sections 3, 5, 7: four working tools, persistence, 9 passing tests, runnable smoke test | Missing measured results (Section 7). `CASES.md`, eval results and `VIDEO_SCRIPT.md` were not in the repo, so the demo video and case writeups are not backed here |
| **Clarity** | Sections 3, 4: short paragraphs, the graph model and queries shown verbatim, the worked example | Section 4 is dense for non-Cypher readers; consider a one-line gloss for each query |
| **Effective use of connected context** | Section 4: the answer comes from traversing Doc -> Rev -> Fact and the SUPERSEDES chain, and the contradiction join depends on graph structure; persistent mode keeps the history | A comparison with a flat/vector baseline (Section 7) is what would make this case convincingly |

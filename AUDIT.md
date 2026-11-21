# Hackathon audit: Supersede (Relate by Neo4j Hackathon)

Audited 21 Nov 2026 on `main` at `bac13d2`. There are no other branches or open PRs (PRs 1-5 are
merged). The low-risk fixes below are on branch `audit-fixes`. Everything here was checked
against the sources listed; nothing is estimated unless marked **estimate**.

**Sources**

- Official Rules: https://relate.devpost.com/rules. The automated fetch returned HTTP 403, so I
  read it in a browser.
- Overview page: https://relate.devpost.com/. I read it in a browser, including the
  "Requirements" checklist, the README template and the judging criteria.
- Relate docs: relatedb.ai/docs. Pages read: `reference/cypher/differences-from-neo4j.md`,
  `reference/limitations.md`, `concepts/storage-and-durability.md`,
  `reference/storage/formats.md`, `guides/storage/read-only-and-follow.md`,
  `concepts/transactions-and-concurrency.md`, `reference/api/python.md`, `guides/serve/mcp.md`,
  `guides/agents/connect-over-mcp.md`, `reference/project.md`.

**Where the two Devpost pages differ.** The Official Rules (Section 5) weight the five criteria
**equally**. The overview page lists different criteria and points: Creativity 10, Relate and
connected context 30, Functionality and completeness 25, Usefulness 20, Documentation and
reproducibility 15. The overview also says a project "can be new or extend something you already
have", while the Rules say "New projects only". The Rules govern. Supersede is new either way.

---

**Update after the `eval-supersession` PR (D5).** Everything below describes the repo as audited
(13-question eval). The eval has since been extended with three case types where supersession and
effective dates disagree (missing date, mistyped date, dropped requirement), 6 new questions in 3
new documents. Re-run with `python eval/run_eval.py` (15 documents, 25 revisions, 46 facts, 19
questions):

| Method | Total | Where it scores |
|---|---|---|
| Supersede | **19/19** | everything |
| newest effective date (`eval/baseline.py`) | 9/19 | misses `authority` 2, `unresolved` 2, and all 6 date-case questions |
| supersession-aware, authority-blind | 15/19 | gets all 6 date-case questions; misses `authority` 2 and `unresolved` 2 |
| authority-aware, supersession-blind | 11/19 | gets all `authority`; misses `unresolved` 2 and all 6 date-case questions |

So each part now earns something: `SUPERSEDES` is worth 6 questions beyond dates, authority 2, and
tie detection 2. Two caveats: the date cases were **designed** to separate dates from `SUPERSEDES`
(how common such metadata problems are in real corpora is unknown), and `withdrawn` rests on the
"a revision replaces the whole previous one" modelling choice. The estimated "connected context" score
in Part B was written before this and has not been re-scored.

---

**Update after the `store-fixes` PR (D6, D7 and the capabilities list).** The `Store` defects in
Part C are fixed and covered by tests (suite: 37 passed, no expected failures):

| Defect (as audited) | Now |
|---|---|
| `history()` stopped after 20 hops | follows the whole chain (`*1..`); tested on 120 revisions |
| a reused fact id overwrote another revision's fact | `ValueError`; first fact left intact; re-asserting in the same revision still updates |
| a document without authority crashed `find_contradictions` | `add_document` requires an integer authority (`ValueError`) |
| a conflict inside one revision was missed by `find_contradictions` | the join uses two `MATCH` clauses; reported with winner `None` |
| missing ids were silent no-ops | `ValueError` for unknown document or revision |
| `SUPERSEDES` cycles were accepted | refused (`ValueError`), including self-loops and indirect cycles |

Behavior change to know about: invalid writes now raise instead of being ignored. The README
documents it ("Strict writes"). Also done: the AI-use disclosure is broadened in `README.md` and
`SUBMISSION.md` (D6), and a Relate-capabilities, third-party and AI-tools statement is in both
(part of D10). Still open: D8 (server opens the store writable), D9 (dependency upper bounds),
D11 (README structure), D12 (ingestion), D15 (Python 3.10, macOS, Linux untested).

---

**Update after the `audit-followups` PR (D8, D9, D10, D11, D12, D15).**

| Item | Now |
|---|---|
| D8 server | opens an existing store **read-only** and refuses a `--db` path that does not exist (a test shows the files stay byte-identical, and that nothing is created) |
| D9 pins | `relate-db>=1.2.0,<1.3`, `mcp>=2,<3`, `pyyaml>=6,<7`, `pytest>=8`; a fresh venv resolves to relate-db 1.2.0 / mcp 2.3.0 / PyYAML 6.0.4 and the suite passes. `anthropic` (optional, `--llm`) is left unpinned |
| D10 | the "demo video shows" sentence is reworded; capabilities list was added earlier |
| D11 | README follows the overview template: Use case / How it uses Relate (Mode, Why this mode, What the graph models) / Setup and run / Where the data lives; Disclosures unchanged word for word |
| D12 | `supersede.ingest` loads annotated Markdown (header plus inline `{{subject.predicate = value}}`); deterministic, no new dependency; **it does not extract facts from unannotated text** |
| D15 | see the CI results recorded in the PR; locally only Windows / Python 3.11 was run |

---

## Part A: Compliance checklist

| # | Item | Status | Evidence |
|---|---|---|---|
| 1 | Repo public, topics, default branch, license | **Pass** | `gh repo view`: PUBLIC, default `main`, topics `agent-memory, mcp, neo4j, relate, relate-neo4j-hackathon`. `gh api repos/.../license`: MIT (`LICENSE`). Dependency licenses from installed metadata: relate-db 1.2.0 Apache-2.0 (classifier, plus `relate_db-1.2.0.dist-info/licenses/LICENSE` = "Apache License Version 2.0"); mcp 2.3.0 MIT; PyYAML 6.0.4 MIT; pytest 9.2.0 MIT. anthropic (optional) is not installed here, so its license is **unverified**. MIT is compatible with all of them. |
| 2 | Started and committed inside the contest period | **Pass** | `git log --all` on `main`: 15 commits, first `9ff162a` at 2026-11-21T14:05:50+02:00 (= 21 Nov 04:05 PST), last on the same day. The period starts 11 Nov 2026 6:00 PM PST (Rules Section 1) and the project must be started on or after that date (Section 3). There is no imported history: the first commit is a single initial commit of files dated 2026-11-21. |
| 3 | Disclosures accurate and consistent | **At risk (minor)** | README "Disclosures" and `SUBMISSION.md` Section 10 agree: start date, concepts reused but no code, fictional data, AI assistance, third-party tools. **Understated:** the AI line says "the code, tests and this README". The corpus, eval, demo script, video script and submission text were also AI-assisted, and the commits carry `Co-Authored-By: Claude` trailers. Rules Section 3 requires describing "any significant AI use". Recommendation D6; not changed. |
| 4 | Relate is load-bearing | **Pass** | Every read and write in `src/supersede/store.py` is Cypher run through `relate.connect` (DB-API, named params). The Relate features used are listed below this table. |
| 5 | Inspectable persistent store | **Fail on `main` → fixed in PR** | The overview checklist asks for a "Persistent Relate store: a directory or single file judges can inspect". Its README template asks for "Where the data lives: Path to the persistent store in this repo", and it says "Include the store in your repo or show it in your demo". `main` has no store: `.gitignore` excludes `*.relate`, and the README has no such section. **Fix:** commit `examples/store/supersede-demo.relate/` (directory mode, 10 files, about 7 KB). See Part C, "Committed store". |
| 6 | README states the Relate mode and why | **Pass** | README: "persistent on-disk store (`--db path`; Relate keeps it as a directory) ... Memory-only would lose the revision history". This is accurate: a store built by `Store(path)` is a directory with `manifest.json`, `nodes/`, `relationships/`, `wal/`, `.relate/schema/`, and the docs (`reference/storage/formats.md`) say any non-`:memory:`, non-`.rl` path is a directory store. |
| 7 | Setup from scratch, README only | **Pass with one failure, fixed** | Fresh `git clone` into an empty folder, Windows 11, Python 3.11.9, total **119 s**: clone 1 s, venv + `pip install -e ".[dev]"` about 85 s, seed, `pytest` **19 passed**, `mcp_smoke.py` exit 0 with 0 bytes on stderr, `run_eval.py` 13/13 vs 9/13, `demo_session.py` exit 0 with 44 lines. **Failure:** the README's `. .venv/bin/activate` doesn't exist on Windows (`No such file or directory`), fixed. The README didn't state a Python version (mcp 2.3.0 needs >= 3.10), fixed. The README's MCP client config silently serves an **empty** store when launched from another folder (Part C), fixed. Dependencies have lower bounds only (`relate-db>=1.2.0`, `mcp>=2`), so recommendation D9. No network calls in the default path: `git grep` finds no `requests`, `urllib`, `httpx` or `socket` in `src`, `examples` or `eval`, and `anthropic` is imported only behind `--llm`. **Not tested:** Python 3.10, macOS, Linux. |
| 8 | Demo video readiness | **Fail (not yet recorded)** | Rules Section 4 requires "a video of up to 2 minutes or a link to a working demo". It must be your own work, third-party music needs permission, and it must be viewable without a login. `VIDEO_SCRIPT.md` is 253 spoken words, and its numbers match `run_eval.py` and `demo_session.py` (12 documents, 13/13, 9/13). No music is planned. The invented names "Veltara Automotive", "Korvin Mobility" and "Brannock Castings" returned no exact-match company in a web search (closest: "Vultara", "Brothock Castings Co"). A silent terminal capture exists locally (`demo_terminal_capture.mp4`, git-ignored). No narrated, uploaded video exists yet. |
| 9 | Submission text readiness | **At risk (minor)** | `SUBMISSION.md` covers title, tagline, description, usefulness, Relate usage, results, Built with, and disclosures. Stale or unbacked items: "The suite has 18 tests" (19 on `main`, 32 on this branch); Section 5 says "which is what the demo video shows" (no video yet); there is no explicit "Product capabilities" list, which Rules Section 4 asks for. The repo link and setup steps go in their own Devpost fields. Recommendation D10. |
| 10 | Hygiene | **Pass, one note** | `git ls-files` shows no `.env`, `.venv`, caches, `*.egg-info`, stray `*.relate` or media. `git grep` finds no keys or tokens (`sk-ant`, `ghp_`, `gho_`, `AKIA`, private keys, `api_key=`), and no standards names or OEM brands (`iatf`, `16949`, `ppap`, `vda`, `aiag`, `ford`, `toyota`, `bmw`, `bosch`). **Note:** 10 commits carry a personal e-mail address as author in public git metadata. Removing it needs a history rewrite, which I did not do; GitHub's "keep my email private" setting prevents it in future. |

**Relate features Supersede uses (item 4)**

- embedded Python DB-API: `relate.connect`, cursors, `$name` parameters, `commit`, `close`
- directory-mode persistence, and `read_only=True` opens (committed store tests)
- `MERGE` upserts
- `NOT (:Rev)-[:SUPERSEDES]->(r)` pattern predicates
- a variable-length path `[:SUPERSEDES*1..20]` with `length(p)`
- a two-pattern join with `<>` and `<`
- `ORDER BY`, `count()`

**Relate features not used:**

- vector or full-text `SEARCH`
- Relate's own MCP server (`relate serve --mcp stdio --read-only`, tools `read_cypher` and `get_schema`)
- the CLI
- Bolt or HTTP
- WebAssembly

---

## Part B: Judge's scorecard (estimate)

The scores are my estimate of a skeptical Neo4j judge. "A strong entry" here means one with a
working demo video, a clear problem, a measurable result and a polished README; this says nothing
about any specific entry.

| Criterion | Score | Why | Single change that raises it most |
|---|---|---|---|
| Creativity | **6** | Revision chains and source authority as graph structure, with an honest `unresolved` on ties, is a sound and well-framed idea. Versioned or bitemporal facts are not new, though; the agent-memory and MCP framing is the fresh part. | One case only a graph answers: a work instruction derived from a superseded procedure revision is flagged stale through a `DERIVED_FROM` edge. |
| Usefulness | **6** | Real problem, named user (quality and compliance teams). There is no ingestion: facts and links are entered through the `Store` API, and the corpus has 34 hand-made facts. | Load facts from documents, even a simple extractor over a few fictional procedure files. |
| Completeness | **7** | Works end to end from a fresh clone in about 2 minutes: tests, MCP over stdio, scripted demo, eval. Missing on `main`: video, inspectable store, a working MCP-client config. The `Store` edge-case defects are in Part C. | Record the video, and merge this PR. |
| Clarity | **7** | Clear README and submission text, Cypher shown verbatim with plain-language glosses, an honest results section. The README doesn't follow the overview's template headings (Use case / How it uses Relate: Mode, Why, What the graph models / Where the data lives). There is no diagram, and the video is pending. | Restructure the README to the overview template and add one graph diagram image. |
| Effective use of connected context | **5** | Real Cypher traversals in embedded Relate with a persistent store. But the ablation in Part C shows that on the 13 questions as audited **`SUPERSEDES` adds nothing over newest-date** (both 9/13), and authority alone reaches 11/13. The graph is shallow (3 labels, 3 relationship types, chains of at most 3), and it uses no retrieval and not Relate's own MCP. | Add eval cases where supersession and effective dates disagree (back-dated corrections, future-effective drafts, a revocation), plus one cross-document reference chain, and report the ablation. |

**Estimated standing:**

- Overview weights: about **61/100** (6×1 + 5×3 + 7×2.5 + 6×2 + 7×1.5).
- Equal weights per the Rules: about **6.2/10**.
- Engineering and honesty are above average. The weakest link is showing that the *graph* makes
  the difference. That criterion carries the largest weight on the overview page.

---

## Part C: Technical review

**Edge-case probes** (`Store`, current behavior; the probe script ran against `main`; the results
are pinned in `tests/test_edge_cases.py`)

| Case | Observed | Verdict |
|---|---|---|
| Cycle r1↔r2 | `current_revisions() == []`, answer `unknown`, `history(r2) == ['A-r1','A-r2']` (contains itself) | No cycle guard. History in a cycle includes the start node. xfail test. |
| A revision superseded by two newer ones | both newer revisions are current; the same document conflicts with itself → `unresolved` | Defensible, but undocumented. Test pins it. |
| Same value, different format (`100%` vs `100 %`) | counted as a contradiction | Known limitation (exact strings). Test pins it. |
| Document with `authority=None` | `Contradiction.winner` raises `TypeError: '>' not supported between NoneType and int`, so the `find_contradictions` MCP tool would error | **Defect.** xfail test. |
| Chain of 25 revisions | `history('A-r25')` returns 20, not 24 | **Defect:** silent truncation by `*1..20` (`store.py`, `history`). Relate allows deeper explicit bounds: the docs say the default limit is 500 hops (max 2000), and `*1..2001` was refused with `TraversalDepthExceeded`. xfail test. |
| Reused fact id in another revision | `MERGE (f:Fact {fid})` rewrites the first fact and links one node to both revisions; `answer("x","p")` becomes `unknown` | **Defect (data corruption)**. `load_corpus.py` guards against it; `Store` doesn't. xfail test. |
| `supersede` or `assert_fact` on missing ids | silent no-op | **Defect** (no error). xfail test. |
| Fact not restated in the newer revision | `unknown` | Design choice: a revision replaces the whole previous one. Worth stating in the README. Test pins it. |
| Two values in one revision | `answer()` says `unresolved`, but `contradictions()` returns `[]` | **Defect:** the two comma-separated patterns would have to bind the same `HAS_REV` relationship twice, which Cypher's relationship uniqueness within one `MATCH` forbids. xfail test. |
| Top authority group agrees, lower one dissents | `resolved` with the top value | Correct. Test pins it. |

The current-revision query, the contradiction join limited to current revisions, and authority
resolution with tie detection are correct for well-formed input.

**Tests added** (all pass or xfail against current behavior; `Store` is unchanged)

- `tests/test_edge_cases.py`: 5 passing tests and 6 `xfail(strict=True)` tests. A defect fix turns
  its test into an unexpected pass, which fails the suite until the marker is removed.
- `tests/test_committed_store.py`: 2 tests.
- Suite on this branch: **26 passed, 6 xfailed** (32 tests). Proposed but not written: MCP tool
  error paths (bad arguments), and history ordering with forks.

**Eval and baseline** (as audited, on the 13-question set; see the update above for the current numbers). These are re-run numbers, using the value-only scoring in
`eval/run_eval.py`; the ablation script is ad hoc and not committed.

| Baseline | Total | stale | authority | unresolved | agreed | unknown | chain |
|---|---|---|---|---|---|---|---|
| newest effective date (`eval/baseline.py`) | 9/13 | 2/2 | 1/3 | 0/2 | 2/2 | 2/2 | 2/2 |
| supersession-aware, authority-blind | **9/13** | 2/2 | 1/3 | 0/2 | 2/2 | 2/2 | 2/2 |
| authority-aware, supersession-blind | **11/13** | 2/2 | 3/3 | 0/2 | 2/2 | 2/2 | 2/2 |
| Supersede | 13/13 | 2/2 | 3/3 | 2/2 | 2/2 | 2/2 | 2/2 |

Reading:

- The baseline is weak but disclosed. Its `unresolved` misses are by construction.
- Two of the three `authority` questions were designed with a newer, lower-authority source.
- In this corpus every superseding revision is also newer-dated, so the stale and chain questions
  never separate supersession from dates.
- The same author wrote the corpus and the questions. That is not tuning to flatter, but the cases
  are a designed set, and `SUBMISSION.md` says so.

**MCP server**

- Tool descriptions and server instructions are clear for an agent.
- Exceptions surface as MCP errors without tailored messages.
- The thread-affinity design matches the Relate docs. A connection belongs to the thread that
  opened it, and use from another thread raises `WrongThread` (`concepts/transactions-and-concurrency.md`).
  `Store` runs everything, including `close`, on one thread. The shutdown fix (PR 3) closes the
  store, and the server's stderr is now empty (smoke test: 0 bytes).
- **The README config as written** (relative `--db demo.relate`, `PYTHONPATH=src`), launched from
  another folder, connected and returned `{'result': []}`, because it created a new, empty
  `demo.relate` in that folder. **Fixed in the README** (absolute paths). With absolute paths and
  the committed store, it answers `10 years` from `CSR-VEL-01-r2`, with 0 bytes of stderr, and
  leaves the committed files unchanged.
- The server opens the store **writable** although every tool only reads. The Relate docs
  recommend `--read-only` for agent-facing stores. See D8.

**Committed store**

- Built by `python examples/load_corpus.py examples/store/supersede-demo.relate`.
- Verified from the *tracked files only* (`git archive` of the index): read-only open gives 12 Doc,
  19 Rev, 34 Fact, 60 relationships.
- A writable open and close left every file byte-identical (SHA-256 over the tree).
- Lock files contain only a constant marker (`CYPHERLITE-LOCK-v1 root`).
- A copy **without** the lock files failed a read-only open ("read-only open requires an existing
  database"), so the whole directory is committed.
- The `*.relate` ignore rule also matched the store's internal `.relate/` folder, so both get
  explicit `!` exceptions.
- `.gitattributes` disables line-ending conversion under `examples/store/`. A CRLF-converted
  `manifest.json` still opened, so this is a precaution.
- Alternative: a single-file `.rl` store (64 KB, no lock files) also opens read-only. I kept
  directory mode so it matches the README's stated mode.

**Relate behavior worth documenting**

- One writing process per store ("storage locked").
- `read_only=True` opens beside a writer.
- A store copy needs its WAL folder.
- Explicit traversal bounds above the depth limit are refused.
- Cypher relationship uniqueness applies across a whole `MATCH` (the same-revision case above).

---

## Part D: Prioritized fix list

| # | Issue | Severity | Criterion | Fix | Effort | Status |
|---|---|---|---|---|---|---|
| D1 | No demo video recorded or uploaded | **Disqualifying if missing at the deadline** (Rules Section 4) | Clarity, completeness | Record the voiceover over the capture, edit to 2:00 or under, upload publicly or unlisted | 2-3 h | You |
| D2 | Devpost entry not submitted | **Disqualifying if missing** (deadline 11 Dec 2026, 6:00 PM PST) | all | Paste `SUBMISSION.md`, repo link, video link; keep the repo public with topic `relate` through 17 Dec | 30 min | You |
| D3 | No inspectable store in the repo | High (overview checklist) | Connected context, docs | Committed `examples/store/supersede-demo.relate/`, README "Where the data lives", tests | done | **This PR** |
| D4 | README MCP config serves an empty store | High | Completeness, reproducibility | Absolute paths, venv Python, a warning about relative `--db` | done | **This PR** |
| D5 | Eval doesn't show what `SUPERSEDES` adds (as audited: ablation 9/13 = 9/13) | High | Connected context (30 on overview), creativity | Add realistic cases where supersession and dates disagree, plus a cross-document reference chain; publish the ablation table | 3-5 h | **Done in the `eval-supersession` PR** (date cases and ablations; no cross-document reference chain yet) |
| D6 | AI-use disclosure understates scope | High (Rules Section 3 requires it) | Eligibility | Say that code, tests, docs, corpus, eval, demo and submission text were AI-assisted | 5 min | **Done in the `store-fixes` PR** |
| D7 | `Store` defects: reused fid corrupts data, `None` authority crashes, history capped at 20, same-revision conflict missing, missing ids silent, cycles unguarded | Medium | Completeness | Validate inputs (fail on unknown ids, duplicate fid, non-int authority); raise or remove the cap; add a same-revision case | 1-2 h | **Done in the `store-fixes` PR** (the xfail tests are now passing tests) |
| D8 | Server opens writable; a missing `--db` path creates a store | Medium | Completeness, connected context | `--read-only` flag (or default) and refuse a non-existent `--db` | 30 min | Needs your OK |
| D9 | Unbounded dependency versions on an experimental product (Rules Section 3) | Medium | Reproducibility | `relate-db>=1.2,<1.3`, `mcp>=2,<3` | 5 min | Needs your OK |
| D10 | `SUBMISSION.md`: "18 tests", unbacked video sentence, no explicit capabilities list | Medium | Clarity | Update the count after merge, drop or keep the video sentence, add "Relate capabilities used" | 10 min | Needs your OK (claims) |
| D11 | README not in the overview template's structure | Medium | Docs (15) | Headings: Use case / How it uses Relate (Mode, Why, What the graph models) / Setup and run / Where the data lives | 30 min | Recommended |
| D12 | No ingestion from documents | Medium | Usefulness | Small loader from fictional text documents | half a day or more | Optional |
| D13 | Windows activation and Python version missing from README | Low | Reproducibility | Added | done | **This PR** |
| D14 | Personal e-mail address in commit metadata | Low (privacy) | none | Leave it (no history rewrite); set a noreply e-mail address for future commits | 2 min | Informational |
| D15 | Untested: Python 3.10, macOS, Linux | Low | Reproducibility | One run on each, or a CI matrix | 30 min | Recommended |

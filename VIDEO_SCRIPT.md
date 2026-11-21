# Demo video script (2:00 maximum)

All numbers come from real runs of `python eval/run_eval.py` and the demo scripts on the fictional
corpus (16 documents, 26 revisions, 47 facts). Re-check them against a fresh run before recording.
The Official Rules say the video must be your own work (filming, editing, graphic design) and may
only use third-party music or images with permission. They do not require a spoken voice: use the
voiceover below, or the captions in the last section.

Record the screen and the voice separately, then line them up in the editor.

## Script (voiceover)

| Time | On screen | What I say |
|---|---|---|
| **0:00-0:12 Hook** | Title card "Supersede", then the README title. | Agents that read documents quote stale or conflicting facts. A procedure is revised, but the old one stays in memory. Vector memory cannot tell what replaced what. |
| **0:12-0:32 Idea** | `docs/graph.svg` (documents, revisions, facts, SUPERSEDES, DERIVED_FROM, authority). Highlight each edge as it is named. | Supersede keeps that structure in a graph, on Relate, the embedded graph database: documents, revisions, facts, which revision supersedes which, and each document's authority. Relate's full-text and vector indexes find the right topic for a question. Cypher traversals decide which fact is in force. |
| **0:32-1:00 Demo, session** | Capture 1: `python examples/demo_session.py --pause 2.5`. Hold on step 1 (baseline `'3 years'` vs Supersede `'10 years'` with the reason), then step 2 winners, step 3 `unresolved`, step 4 history. | A naive baseline takes the newest fact: three years, from a shift note. Supersede answers ten years, from the customer requirement, and says why. It lists real conflicts with a winner by authority, reports an equal-authority conflict as unresolved instead of guessing, and keeps only the newest revision. |
| **1:00-1:20 Demo, plain language** | Capture 2: `python examples/ask.py "What sampling rule applied?" --as-of 2025-07-01`, then `python examples/ask.py "Which form do inspectors fill in for final inspection results?"` (the red `STALE` line; `ask.py` colours its output on a real terminal). | Ask in plain language, for any date. What sampling rule applied in July 2025? And this form number comes with a warning: its source was written from a procedure revision that has since been replaced. |
| **1:20-1:33 Agent and web** | `docs/agent_transcript.md` (the equal-authority answer), then the web page `python web/app.py` (or the deployed one, https://supersede-demo.onrender.com): pick `final_inspection / sampling` and **drag the date slider** across 2024, 2025 and 2026 so the gold outline jumps from bar to bar and the answer changes. | A real Claude agent uses the same server over MCP, and refuses to pick between equal-authority sources. And in the web demo you drag the date and watch the answer change. |
| **1:33-1:52 Result** | The final lines of `python eval/run_eval.py` (the plain-language and revision sections). | On twenty-three plain-language questions Supersede answers all twenty-three; the same search with a newest-date answer gets thirteen. On nineteen revision questions it gets all nineteen against nine. The data is fictional, and real documents are messier. |
| **1:52-2:00 Close** | Repo page `github.com/sergiunicoara/supersede`, MIT license visible, text "Built with Relate by Neo4j". | Open source, MIT licensed, at github dot com slash sergiunicoara slash supersede. Built with Relate by Neo4j. |

The slider works on a local `python web/app.py` too, so the video does not need the demo to be deployed. This is the most visual moment: give it a full 5 to 6 seconds of slow dragging.

## Notes on the claims

* "23 of 23 against 13": right topic first 23/23; correct answer end to end 23/23 for `ask()`, against
  13/23 for the same retrieval answered by the newest date (name-overlap retrieval: 10/23). The first
  run was 22/23 before "many" and "much" were added to the stop words, so do not call it a blind result.
* "19 against 9": 19/19 on the original answer questions against the newest-date baseline's 9/19.
  Part of the baseline's gap is by construction (no baseline can report a disagreement) and the
  date cases were designed to separate dates from `SUPERSEDES`; the README says so.
* "Real documents are messier" stands in for the caveat that every result is on fictional data.
* Step 1 shows a baseline answer that is newer but outranked, not a superseded one. Do not call the
  baseline value "stale" on screen. The red `STALE` line in the form-number answer is a different
  thing: a revision written from a source that was later replaced.
* The agent transcript misreads one tool result in its last answer; show only the equal-authority answer.

## Recording checklist

**Setup**
- [ ] Terminal font 18-20 pt, dark theme. Window about 100 columns wide (the longest line is 88).
- [ ] Hide notifications, close other windows, clear the prompt.
- [ ] 1920x1080, 30 fps. Record the screen without audio; record the voice separately.
- [ ] Colours only show on a real terminal and when `NO_COLOR` is not set.

**Commands before recording** (PowerShell, from the repo root, on `main`)

```powershell
git checkout main
.venv\Scripts\activate
pip install -e ".[dev]"
python -m pytest -q
python eval\run_eval.py
```

**Capture 1** (about 38 s): `cls; python examples\demo_session.py --pause 2.5`

**Capture 2** (about 20 s): run the two `ask.py` commands from the table, one after the other, with a
two-second pause between them.

**Capture 3** (about 10 s, a browser window, not the terminal): open http://127.0.0.1:7860 after `python web/app.py`,
scroll to "Watch the answer change over time", and drag the slider slowly from early 2024 to 2026.

Nothing needs resetting: the demo builds its store in a temporary folder, and `ask.py` opens the
committed store read-only.

**If it runs long, cut in this order**
1. The agent and web segment (1:20), shorten to the transcript alone.
2. Step 4 of the demo session.
3. The second `ask.py` command.
4. In the idea section, "Relate's full-text and vector indexes find the right topic for a question."

Keep the baseline-versus-Supersede comparison, the equal-authority step, and the results.

**Before upload**
- [ ] Final length at or under 2:00 (hard limit).
- [ ] Numbers on screen match the spoken numbers (23/23 and 13/23; 19/19 and 9/19; sixteen documents).
- [ ] No API keys, usernames or paths visible in the terminal; no unlicensed music or images.
- [ ] Viewable without a login (public or unlisted link).

## Captions instead of a voice (allowed by the rules)

Place one caption at the start of each segment, white text on a dark band, 2 to 4 seconds per line.

| Time | Caption |
|---|---|
| 0:00 | Agents quote stale or conflicting facts from documents. |
| 0:06 | A procedure is revised, but the old one stays in memory. |
| 0:12 | Supersede: a graph on Relate (embedded graph database). |
| 0:20 | Revisions, supersession and authority are graph structure. |
| 0:27 | Relate's full-text and vector indexes find the topic; Cypher decides the fact in force. |
| 0:32 | Naive baseline: newest fact = 3 years (a shift note). |
| 0:40 | Supersede: 10 years, from the customer requirement, with the reason. |
| 0:48 | Equal-authority conflict: reported as unresolved, not guessed. |
| 0:56 | Only the newest revision counts. |
| 1:00 | Ask in plain language, for any date. |
| 1:10 | Warning: this source was written from a procedure revision that was replaced. |
| 1:20 | A real Claude agent uses the same MCP server. Drag the date: the answer changes with the revisions. |
| 1:33 | 23 plain-language questions: 23 correct (same search, newest date: 13). |
| 1:41 | 19 revision questions: 19 correct (newest-date baseline: 9). |
| 1:47 | Fictional data; real documents are messier. |
| 1:52 | Open source, MIT. github.com/sergiunicoara/supersede |
| 1:56 | Built with Relate by Neo4j. |

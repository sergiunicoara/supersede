# Demo video script (2:00 maximum)

All numbers below come from real runs of `examples/demo_session.py` and `eval/run_eval.py` on the
fictional corpus: 12 documents, 19 revisions, 34 facts; 13 questions; Supersede 13/13, naive
baseline 9/13. Re-check them against a fresh run before recording.

The right-hand column is the voiceover, written to be read as is. Record the screen and the voice
separately, then line them up in the editor.

## Script

| Time | On screen | What I say |
|---|---|---|
| **0:00-0:15 Hook** | Title card: "Supersede", then a terminal with a document list (`ls examples/corpus`), or just the title over a dark background. | Agents that read documents have a memory problem. A procedure gets revised, but the old version stays in memory. Two documents disagree, and the agent quotes whichever came back first. Vector memory has no idea what replaced what. |
| **0:15-0:35 Idea** | The README snippet showing `(Doc {authority})-[:HAS_REV]->(Rev)-[:ASSERTS]->(Fact)` and `(Rev)-[:SUPERSEDES]->(Rev)`, or a simple four-box diagram of the same. Highlight `SUPERSEDES` and `authority` as they are named. | Supersede models that structure as a graph. A document has revisions. A revision asserts facts. A newer revision supersedes an older one, and every document has an authority level. Current simply means not superseded. It runs on Relate, an embedded graph database: Cypher queries, inside the same process, no server. |
| **0:35-0:41 Demo, intro** | Terminal, `python examples/demo_session.py --pause 4` starts; the header lines appear (corpus size, four MCP tools). | This is an agent session over a fictional quality corpus, talking to Supersede through its MCP server. |
| **0:41-0:54 Step 1, the centerpiece** | STEP 1. Baseline line: `'3 years'` from `SN-0914-r1 (shift note, authority 1)`. Then Supersede: `'10 years'` from `CSR-VEL-01-r2`, the reason line and the two `overruled` lines. Hold on this frame. | How long must retained samples be kept? The naive baseline takes the newest fact, a night-shift note: three years. Supersede answers ten years, from the customer requirement, with the reason and what it overruled. |
| **0:54-1:10 Step 2** | STEP 2. The conflict list scrolls in; the winner lines are visible. | Next, find contradictions. It only compares current revisions, so old values are never conflicts. Each conflict comes with a winner, chosen by document authority. |
| **1:10-1:18 Step 3** | STEP 3. `unresolved`, with the two candidates `500 parts` and `400 parts`. | Two work instructions of equal authority disagree. Supersede says unresolved, and does not guess. |
| **1:18-1:26 Step 4** | STEP 4. `QP-07-r3 replaced QP-07-r2, then QP-07-r1`, then `'5 years'`. | Finally, revision history: revision three replaced two, then one. Only the newest counts. |
| **1:26-1:35 Demo, wrap** | Final eval line appears; hold on it. | Same documents, same question. The difference is the graph structure. |
| **1:35-1:50 Result** | The eval line: `Supersede 13/13` vs `naive baseline 9/13`. Optionally cut to the `run_eval.py` table. | On thirteen questions over twelve fictional documents, Supersede answers all thirteen correctly. The naive baseline gets nine. It fails when a lower-authority source is newer, and when sources conflict. Real documents will be messier. |
| **1:50-2:00 Close** | Repo page `github.com/sergiunicoara/supersede`, MIT license visible, "Built with Relate by Neo4j" as a text line. | Supersede is open source, MIT licensed, at github dot com slash sergiunicoara slash supersede. Built with Relate by Neo4j. |

## Notes on the claims

* "Fails when a lower-authority source is newer": true for 2 of the 13 questions (retention period,
  film thickness). "And when sources conflict": the 2 equal-authority questions, which the baseline
  cannot pass by design because it never reports a disagreement. Both are explained in
  `eval/run_eval.py`.
* The baseline gets the stale, agreed, unknown and chain questions right (9 of 13). Do not imply it
  fails everywhere; the script does not.
* Step 1 shows a baseline answer that is newer but outranked, not a superseded one: in this corpus
  newest-wins never returns a superseded revision. Do not call the baseline value "stale" on screen.

## Recording checklist

**Setup**
- [ ] Terminal font 18-20 pt (readable at 1080p after compression), dark theme, high contrast.
- [ ] Window about 100 columns wide (the longest output line is 88 characters). Full output is 44
      lines: make the window tall enough for that, or accept a scroll between steps 2 and 3.
- [ ] Hide notifications, close other windows, and clear the prompt (`cls`).
- [ ] Resolution 1920x1080, 30 fps. Record the screen without audio; record the voice separately.
- [ ] Check colours on a real terminal first. They only show when output is a terminal and
      `NO_COLOR` is not set. Winners are also marked in plain text.

**Commands before recording** (PowerShell, from the repo root)

```powershell
git checkout demo-corpus
.venv\Scripts\activate
pip install -e ".[dev]"
python -m pytest -q
python eval\run_eval.py
```

Nothing needs resetting for the default run: `demo_session.py` builds a fresh store in a temporary
directory and deletes it afterwards, so `demo.relate` is not used. If you pass `--db`, the path
must not exist (`Remove-Item -Recurse -Force .\mydemo.relate` first).

**Record** (about 55 s of screen at this pace, plus about 3 s of startup to cut)

```powershell
cls; python examples\demo_session.py --pause 4
```

Measured total run time (startup included): 23 s at `--pause 1.5`, 36 s at 2.5, 42 s at 3.
At `--pause 4` expect about 55 s. Do a dry run and time it on your machine.

**Alignment.** On screen at `--pause 4`, step 1 stays up about 12 s, step 2 about 16 s, steps 3 and
4 about 8 s each, and the intro about 6 s. The spoken lines are written to fit those windows. Step
1 is the tightest; if the voice runs past it, freeze its last frame in the editor.

**If it runs long, cut in this order**
1. Step 4 (revision history): drop the row and its line (about 14 words, 8 s).
2. Shorten step 2: speed up the conflict list or stop after the first two conflicts. Cut "Each
   conflict comes with a winner, chosen by document authority."
3. The wrap line "Same documents, same question. The difference is the graph structure."
4. In the idea section, drop "Current simply means not superseded."

Keep step 1, step 3 and the result: they carry the story.

**Before upload**
- [ ] Final length at or under 2:00 (hard limit).
- [ ] The numbers on screen match the spoken numbers: 13/13 and 9/13, twelve documents.
- [ ] No API keys, usernames or paths visible in the terminal.

# Evidence: every measurement, and how to read it

Everything here can be re-run: `python eval/run_eval.py` (deterministic, offline) and
`python eval/run_extraction_eval.py [--dir examples/real]` (live, needs an API key).

## How to read these numbers

* **Designed cases.** Most test cases were written by me to exercise a behavior. They show that the behavior
  works, not how often real documents need it.
* **Blind versus informed.** Where a run revealed a wording problem and I fixed it, the first run is reported as
  the blind result and later runs as informed. The fixes are listed next to the numbers.
* **Baselines are deliberately simple.** "Newest date wins" is a naive baseline, and two ablations each keep one
  part of the graph. The newest-date baseline is scored on the value only, which is generous to it.
* **Strings, not meaning.** Values are compared as exact strings, so `2 years` and `two years` are different values.
* **Small samples.** The real-text set is 16 documents in 7 chains that I chose.

## 1. Revision questions (fictional corpus)

16 documents, 26 revisions, 47 facts; 19 questions, two or three per case (`examples/corpus/CASES.md`). A
Supersede answer is correct only if the status, the value and the source revision all match.

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

* In the first six case types a newer revision is also newer by date, so newest-date and "follow `SUPERSEDES`"
  agree, and the baseline gets those right. My first eval had the baseline at 9 of 13 and the supersession-aware
  ablation level with it, which is why I added the next three case types.
* `missing_date`, `date_error` and `withdrawn` are about missing, wrong or irrelevant metadata. Date-based methods
  fail all six questions; following `SUPERSEDES` answers all six. **I designed these cases to separate the two, and
  I do not know how often such problems occur in real corpora.**
* The baseline's two `authority` errors are a lower-authority source that is newer than the controlling one.
  Authority alone fixes them. Its two `unresolved` misses are by construction: no baseline can report a
  disagreement. Following `SUPERSEDES` is worth 6 of the 19 questions beyond dates, authority 2, tie detection 2.
* `withdrawn` rests on a modelling choice: a revision replaces the whole previous one, so a fact it does not restate
  is not in force. Supersede cannot tell a deliberate withdrawal from a requirement the author forgot to carry over.
* Lineage (`DERIVED_FROM`): 3 of 3 checks. The baselines keep no derivation structure and are not scored on it.

## 2. Plain-language questions and "what was in force on this date?"

Deterministic, in the same `run_eval.py`.

| 23 plain-language questions (4 off-topic) | Right topic first | Correct answer end to end |
|---|---|---|
| **Supersede `ask()`** (Relate full-text + graph) | **23/23** | **23/23** |
| same retrieval, answered by newest date | 23/23 | 13/23 |
| name-overlap retrieval, answered by newest date | 17/23 | 10/23 |

Retrieval alone is not the point: the same retrieval with a newest-date answer gets 13 of 23. The first run was
22/23: one off-topic question ("How many holidays do employees get?") matched a topic only through the generic
words "how many". I then added "many" and "much" to the stop words, a change informed by that miss, so 23/23 is not
blind.

13 "what was in force on this date" questions, including the mistyped-date and missing-date documents:
**Supersede 13/13** against 11/13 for "the newest fact dated on or before that day". Effective dates are taken at
face value, and every problem that could affect an answer (blank, unreadable, future, earlier than the revision it
replaces) is reported in `warnings`. One case is a known limit and is in the eval on purpose: a revision with no
effective date cannot be placed on the timeline, so for a later date the answer is still the older value, with a
warning, while today's answer (which follows the revision chain) is the newer one.

## 3. Extraction from unannotated text (fictional prose)

`supersede.extract` asks a Claude model for facts, constrained so it cannot corrupt the graph: only keys from a
vocabulary you supply, a verbatim quote for every fact (which must really appear in the document and contain the
value), rejections listed and never written, and a review copy for a human before anything is loaded.

8 documents, 18 gold facts written before any model ran, with traps (a value that used to apply, a rejected option,
distractor numbers, one note with nothing to extract).

| Run | Precision | Recall | Graph answers identical to gold |
|---|---|---|---|
| 1: vocabulary without a value-format rule (blind) | 0.67 | 0.67 | 6 of 10 keys |
| 2: after clarifying the value format | 1.00 | 0.94 | 9 of 10 |
| 3: same, repeated | 1.00 | 1.00 | 10 of 10 |
| 4: same, repeated | 1.00 | 0.94 | 9 of 10 |

All six misses in run 1 were one value-format difference (`2.5 bar` instead of `2.5`). I then added the format rule
to the vocabulary, so runs 2 to 4 are informed. The only fact that varies is an ambiguous sentence the model
sometimes declines to map. The model extracted no historical or rejected value and invented nothing; the guard rails
rejected nothing.

## 4. Real regulation text, including quality manufacturing

`examples/real/` holds text from the public eCFR (US federal regulations, public domain), fetched and checked by me.
The quality-manufacturing part is FDA's device quality regulation, 21 CFR Part 820, in its 2016 form (Quality System
Regulation) and 2026 form (Quality Management System Regulation, which incorporates ISO 13485 by reference):

* **A requirement that leaves the text.** 820.180(b) (2016) says records must be kept for the device's design and
  expected life "but in no case less than 2 years". The 2026 text (820.35) states no period; it defers to ISO 13485, a
  copyrighted standard that is not in the CFR text. Supersede answers `2 years` for a date before 2026 and `unknown`
  today.
* **A complaint-record item that disappears** ("the dates and results of the investigation").
* **The regulation renames itself** across three versions of 820.1.
* Two Federal Acquisition Regulation sections add real dollar thresholds that changed ($5.5M, $6M, $7.5M and $7M,
  $7.5M, $9M).

At that point the folder had 13 documents (20 gold facts, written before any model ran; two documents are expected to
give no facts, to check that the model does not add requirements the text does not state):

| Run | Facts right (of 20) | Graph answers identical to gold, per (key, date) |
|---|---|---|
| 1: first, blind for the new quality keys | 17 (precision 0.85, recall 0.85) | 38 of 48 |
| 2 to 4: after clarifying the vocabulary | 20, 20, 20 | 48 of 48, three times |

The model extracted nothing from the two no-fact documents and added no requirement that is not in the text (it did
not recall the ISO 13485 retention rule). The three misses in run 1 were my own wording problems ("The dates and
results of the investigation" copied with its capital "The"; "quality system" read for the regulation's name). I
clarified the vocabulary and left the gold unchanged, so runs 2 to 4 are informed. The FAR sections followed the same
pattern earlier (13 of 15, then 15 of 15 three times).

## 5. A real authority hierarchy: a regulation over the FDA guidance written from it

The fictional corpus uses a four-tier authority scheme from internal company documents, which I cannot publish real
examples of. A real, public hierarchy exists in the same domain: a regulation outranks non-binding FDA guidance.
FDA's 2016 guidance *Medical Device Reporting for Manufacturers* (US government work, public domain; excerpted in
`examples/real/`, with passages copied verbatim from the PDF and checked by me) still cites 21 CFR 820.198 eleven
times, a section removed in 2026, although a note added to its first page says complaint handling now sits in ISO
13485 clause 8.2.2, so it contradicts itself. Tested offline on the gold facts, Supersede:

* answers today with the regulation (`Clause 8.2.2 in ISO 13485`, authority 4) and lists the guidance's
  `21 CFR 820.198` (authority 2) as overruled;
* treats the guidance as the only statement in force for a date before the rule changed (for example 2020-01-01);
* flags the guidance as written from revisions of 820.198 and 803.18 that were since replaced;
* shows a known limit on real data: the regulation's "2 years" and the guidance's "two years" mean the same but are
  compared as strings, so it is settled by authority (correctly) instead of recognised as agreement.

Live extraction on the 16 documents (29 gold facts): the first, blind run on the new keys got 24 of 27 right
(precision 0.86, recall 0.89); two of the misses were errors in my gold (identical 820.35 text had different gold in two
documents; I had missed a statement the key description asks for) and one value was overlong and **rejected by the
guard rails**. After I corrected those two gold facts and clarified the wording (informed), three runs got 27 of 29
with no wrong fact. The two remaining misses are string boundaries (`21 CFR 820.198(a)` against `21 CFR 820.198`; "The
dates and results..." with its article, which had been right in earlier runs). I stopped there instead of adjusting
until it said 29 of 29.

## 6. A real agent, and a web page

* `examples/agent_demo.py` lets a Claude model use the MCP tools with no script. A verbatim recorded run is in
  `docs/agent_transcript.md`: it declines to pick between two equal-authority sources, uses `answer_as_of` for a past
  date, flags a stale source, and says it does not know when no topic matches. In its last answer it misreads one tool
  result, which the file shows as is.
* `web/app.py` is a read-only page over the committed fictional store (standard library only, no keys, no writes). I
  built and ran it as a Docker image to verify it (`docs/DEPLOY.md`).

## 7. Limits

* **Mostly fictional data.** Real text covers 16 documents in 7 chains, and the hierarchy case is a regulation over
  guidance, not a plant's own tiers (customer requirement > procedure > work instruction > shift note). Real company
  documents, shift notes and emails are untested.
* **Designed cases and informed runs** (see above): treat them as demonstrations of behavior, not benchmarks.
* **Exact-string values:** `100%` against `100% inspection`, or `2 years` against `two years`, count as different.
* **A revision replaces the whole previous one:** a fact it does not restate is no longer in force.
* **Authority is one integer per document.** It cannot say that a lower-ranked source is correctly more specific.
* **Dates are taken at face value.** Bad dates are reported, not repaired, and an undated revision cannot end its
  predecessor.
* **Extraction needs a vocabulary and a document header,** is not deterministic, and sends text to an API.
* **Platforms:** CI covers Linux, macOS and Windows with Python 3.10 to 3.13; I ran things by hand on Windows only.

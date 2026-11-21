# Real documents: US federal regulations with real revision history

Unlike the rest of this repo, the text here is **not fictional**. It is the text of US federal
regulations taken from the eCFR (https://www.ecfr.gov) at dated versions, plus one FDA guidance document:
16 documents in 7 chains.
United States federal regulations are works of the US government and are in the public domain. The
text is as published, with whitespace normalised.

## Quality manufacturing: 21 CFR Part 820 (FDA medical-device quality regulation)

FDA rewrote its device quality regulation: the Quality System Regulation (QSR) became the Quality
Management System Regulation (QMSR), which incorporates ISO 13485 by reference. The eCFR shows both eras.

| Chain | Revisions | What changed |
|---|---|---|
| Record requirements | r1 = 21 CFR 820.180 (2016-12-30), r2 = 21 CFR 820.35 (2026-02-04) | 820.180(b) required records to be kept for the device's design and expected life "but in no case less than 2 years" from release. The 2026 text of 820.35 states **no retention period**: it defers to clause 4.2.5 of ISO 13485 (a copyrighted standard that is not in the CFR text and not in this repo). Supersede therefore answers `unknown` for the retention period today, and `2 years` for a date before 2026 |
| Complaint records | r1 = 21 CFR 820.198 (2016-12-30), r2 = 21 CFR 820.35 (2026-02-04) | the 2016 investigation record had to include "the dates and results of the investigation"; the 2026 list of complaint-record items has no such item |
| Scope | r1, r2, r3 = 21 CFR 820.1 (2016-12-30, 2020-04-02, 2026-02-04) | the regulation calls itself "this quality system regulation", then, in 2026, "this quality management system regulation (QMSR)" |

How I mapped sections into chains (my interpretation, not an official mapping): the 2026 section 820.35
"Control of records" repeats the confidentiality paragraph of 820.180(a) word for word and the complaint
wording of 820.198, so I treated it as the successor of both. The same 820.35 text therefore appears
as revision 2 of two chains. The 2026 text of 820.180 and 820.198 no longer exists in the eCFR.

## A real authority hierarchy: a regulation, and the FDA guidance written from it

The same domain has documents at different authority levels. FDA's guidance *Medical Device Reporting for
Manufacturers* (issued 2016-11-08, https://www.fda.gov/media/86420/download; guidance is a US government work and
in the public domain) is **non-binding** and ranks below the regulation it explains (authority 2 against 4). It was
written from the 2016 text of 21 CFR 820.198 and 803.18, and records that with `derived_from`.

| What | The regulation today | The guidance |
|---|---|---|
| Where complaint handling is required | 21 CFR 820.35(a) plus Clause 8.2.2 of ISO 13485 (820.198 was removed in 2026) | the body still cites **21 CFR 820.198** (11 times); a note added to the first page says complaint handling is now in ISO 13485 clause 8.2.2, so the guidance contradicts itself |
| How the MDR must be evaluated | 803.18(e): "the quality management system requirements described in part 820" (2026-02-02); before that "quality system requirements" | "the complaint file requirements in 21 CFR 820.198" |
| MDR file retention | 803.18(c): "2 years" | "two years" (same meaning, different words) |

What Supersede does with it, tested offline:

* **Authority:** today the regulation's statement wins and the guidance's is listed as overruled.
* **Time:** before the rule changed (for example on 2020-01-01) the guidance is the only statement in force, and
  the 2016 wording of 803.18(e) is the regulation's.
* **Stale lineage:** `stale_derivations` flags the guidance, because it was written from revisions of 820.198 and
  803.18 that have since been replaced, and names what replaced them.
* **A known limit, shown on real data:** the regulation's "2 years" and the guidance's "two years" mean the same, but
  values are compared as strings, so it is settled by authority (correctly) rather than recognised as agreement.

The guidance file is an **excerpt**: five passages copied verbatim from the PDF (I extracted the PDF text myself and
checked each passage), not the whole document. The excerpt includes the first-page note, so it is not made to look
more outdated than it is.

## Procurement compliance: Federal Acquisition Regulation (48 CFR)

| Section | What changed between versions |
|---|---|
| 48 CFR 13.000 (FAR 13.000, scope of the simplified acquisition part) | the ceiling for Subpart 13.5 commercial-item procedures: $7 million, then $7.5 million (2020-10-02), then $9 million (2025-10-01); the 13.500(c) figure $13 million became $15 million |
| 48 CFR 3.1004 (FAR 3.1004, contract clauses) | the contract-value threshold for the ethics clause and the hotline-poster clause: $5.5 million, then $6 million (2020-10-02), then $7.5 million (2025-10-01); the 120-day performance period did not change |

## Provenance and limits, so nobody over-reads this

* The dates come from the eCFR versioner API (`/api/versioner/v1/versions/title-NN.json?part=...&section=...`).
  The earliest version of each section is dated 2016-12-30 or 2017-01-01 only because that is the start of
  the eCFR's history window; **it is not the original effective date**, and earlier values were in force before it.
* Other versions of the FAR sections (2021-11-04, 2021-12-06, 2025-08-27) change wording ("commercial
  items" to "commercial products") but no figure, and are left out; I checked that the dollar figures
  equal their neighbours. 820.1 has a version between the two shown that changes only a telephone and
  room number and a defined-term wording.
* It is 16 documents in 7 chains, an author-chosen sample. It shows extraction and supersession on real
  text; it is not a benchmark.
* Authority is 4 for the regulations (a federal regulation outranks everything else in this repo's scheme) and 2 for
  the one non-binding guidance document. Statutes (which would rank above regulations) are not included.
* A statute > regulation > guidance order is a real hierarchy someone else defined. It is **not** the same as a
  plant's tiers (customer requirement > procedure > work instruction > shift note): it shows the authority mechanism
  working on a real hierarchy, not that those four tiers match how a factory ranks its documents.

Files: `*_r1..r3.md` (one revision each, with the usual header), `vocabulary.json` (the keys to extract),
`gold.json` (the expected facts, written from the text before any model was run; two documents are
expected to give **no** facts, which tests that the model does not add requirements that are not in the text).

Try it (needs `pip install -e ".[llm]"` and `ANTHROPIC_API_KEY`; it sends this public text to the API):

```bash
python eval/run_extraction_eval.py --dir examples/real
```

The offline tests (`tests/test_real_documents.py`) check the real history with the gold facts and need
no key: today's values, values on past dates, a requirement that never changed, and one that left the text.

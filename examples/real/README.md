# Real documents: two US federal regulation sections with real revision history

Unlike the rest of this repo, the text here is **not fictional**. It is the text of two sections of the
Federal Acquisition Regulation (48 CFR), taken from the eCFR (https://www.ecfr.gov) at three dated
versions each. United States federal regulations are works of the US government and are in the
public domain. The text is as published, with whitespace normalised.

| Section | What changed between versions |
|---|---|
| 48 CFR 13.000 (FAR 13.000, scope of the simplified acquisition part) | the ceiling for Subpart 13.5 commercial-item procedures: $7 million, then $7.5 million (2020-10-02), then $9 million (2025-10-01); the 13.500(c) figure $13 million became $15 million |
| 48 CFR 3.1004 (FAR 3.1004, contract clauses) | the contract-value threshold for the ethics clause and the hotline-poster clause: $5.5 million, then $6 million (2020-10-02), then $7.5 million (2025-10-01); the 120-day performance period did not change |

Provenance and limits, so nobody over-reads this:

* The dates come from the eCFR versioner API (`/api/versioner/v1/versions/title-48.json?part=...&section=...`).
  The earliest version of each section is dated 2017-01-01 only because that is the start of the eCFR's
  history window; **it is not the original effective date**, and the earlier values were in force before it.
* Each section has other versions (2021-11-04, 2021-12-06, 2025-08-27) that change wording ("commercial
  items" to "commercial products") but no figure. They are left out; I checked that the dollar figures
  in them equal their neighbours.
* This is procurement compliance, not quality manufacturing, and it is only 6 documents. It shows
  extraction and supersession on real text; it is not a benchmark.
* Authority is 4 for all of them (a federal regulation outranks everything else in this repo's scheme).

Files: `FAR-13-000_r1..r3.md`, `FAR-3-1004_r1..r3.md` (one revision each, with the usual header),
`vocabulary.json` (the keys to extract), `gold.json` (the expected facts, written from the text before
any model was run).

Try it (needs `pip install -e ".[llm]"` and `ANTHROPIC_API_KEY`; it sends this public text to the API):

```bash
python eval/run_extraction_eval.py --dir examples/real
```

The offline tests (`tests/test_real_documents.py`) check the real history with the gold facts and need
no key: today's threshold, the threshold on past dates, and an unchanged requirement.

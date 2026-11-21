# A real agent using Supersede over MCP

Recorded 2026-11-21 with `claude-sonnet-5-5` driving the MCP server over stdio against the
committed demo store (fictional data). The model chose the tools itself. Output is verbatim; the model is
not deterministic, so a re-run may word things differently.

## For how long do we have to store the reference samples we keep from each lot?

* tool call: `ask({"question": "How long must reference samples retained from each lot be stored?"})`

**Agent:** Retained samples from each lot must be kept for **10 years**. This comes from CSR-VEL-01-r2. It wins because its authority level (4) is higher than the conflicting sources: QP-15-r1 says 5 years (authority 3) and SN-0914-r1 says 3 years (authority 1). The tool returned no stale-source or date warnings for this answer.

## After how many parts do we swap the cutting tools in the machining cell?

* tool call: `ask({"question": "After how many parts do we swap the cutting tools in the machining cell?"})`

**Agent:** The sources disagree, so I can't give you one answer. The tool change interval for the machining cell is unresolved.

- **WI-20 (rev WI-20-r1):** 500 parts.
- **WI-24 (rev WI-24-r1):** 400 parts.

Both documents have the same authority level (2), and neither supersedes the other. Someone needs to decide which work instruction governs, and the other should then be revised or retired.

## What inspection sampling rule applied in July 2025?

* tool call: `ask({"question": "What inspection sampling rule applies?", "as_of": "2025-07-31"})`
* tool call: `answer_as_of({"subject": "final_inspection", "predicate": "sampling", "date": "2025-07-01"})`
* tool call: `date_warnings({})`

**Agent:** In July 2025, final inspection sampling followed **AQL 1.0**. The source is QP-07-r2, and the answer was the same on both 1 July and 31 July 2025.

QP-07 has authority 3, so it outranks WI-12-r1, which has authority 2 and calls for 100% inspection. WI-12-r1 is overruled.

There is one date warning in the store, for QP-22-r1, which is dated 2052. It doesn't bear on this sampling rule.

## Which form do inspectors fill in for final inspection, and can I rely on the document it comes from?

* tool call: `ask({"question": "Which form do inspectors fill in for final inspection?"})`
* tool call: `stale_derivations({})`

**Agent:** Inspectors fill in **FORM-9** for final inspection. The only source for that is WI-52-r1, and no other source disagrees.

You shouldn't rely on it without checking. WI-52-r1 was written from QP-07-r1, two derivation hops back, and QP-07-r1 has since been replaced by QP-07-r3. The form number may be out of date. Check QP-07-r3 and update WI-52 if it names a different form.

## Who is the plant manager?

* tool call: `ask({"question": "Who is the plant manager?"})`
* tool call: `current_answer({"subject": "plant", "predicate": "manager"})`
* tool call: `current_revisions({})`

**Agent:** I can't tell you who the plant manager is. The documents don't say.

The plain-language search found no matching topic. A direct lookup of plant and manager returned "no current fact asserted." The only current revision in the store is CSR-KOR-01-r1, and I didn't find a plant manager in it.


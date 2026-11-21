# Corpus cases

The corpus in this folder is **fictional**: an invented casting supplier (Brannock Castings Ltd),
invented customers (Veltara Automotive, Korvin Mobility), invented document numbers, values and
dates. It contains no real standards text and no client data.

Authority levels: **4** customer-specific requirement, **3** controlled procedure, **2** work
instruction, **1** shift note or email. Higher authority wins; equal authority is reported as
`unresolved`.

Each case below has a `Case` slug. `eval/questions.yaml` tags every question with one of these
slugs, and a test checks that every case here has at least one question.

## Case `stale`: an old revision disagrees with the current one

The old revision says X, the current revision says Y. The old value is history, not a conflict.

* `QP-11` r1 says gauge calibration interval is `12 months`; r2 (supersedes r1) says `6 months`.
* `WI-21` r1 says cure time is `40`; r2 says `35`.

Expected: `agreed` with the current value. `find_contradictions` must not report either pair.

## Case `authority`: a cross-document conflict resolved by authority

Current facts in different documents disagree and the owning documents have different authority.

* `final_inspection / sampling`: `QP-07` r3 (authority 3) `AQL 0.65` vs `WI-12` r1 (authority 2)
  `100% inspection`. Procedure wins.
* `retained_sample / retention_period`: `CSR-VEL-01` r2 (4) `10 years` vs `QP-15` r1 (3) `5 years`
  vs `SN-0914` r1 (1) `3 years`. Customer requirement wins, although the shift note is the
  most recently dated.
* `paint_line / film_thickness_um`: `CSR-KOR-01` r1 (4) `70-90` vs `WI-21` r2 (2) `60-80`.
  Customer requirement wins, although the work instruction is more recently dated.

Expected: `resolved`, with the highest-authority value and its source revision.

## Case `unresolved`: an equal-authority conflict

Two current facts disagree and their documents have the same authority. Supersede must say so
instead of guessing.

* `machining_cell / tool_change_interval`: `WI-20` r1 `500 parts` vs `WI-24` r1 `400 parts`
  (both authority 2).
* `line_3 / changeover_target_min`: `SN-0914` r1 `30` vs `EM-2271` r1 `25` (both authority 1).

Expected: `unresolved`, no value.

## Case `agreed`: sources agree

Current facts in several documents state the same value.

* `supplier_audit / frequency`: `CSR-VEL-01` r2, `CSR-KOR-01` r1 and `QP-18` r3 all say `annual`.
* `customer_notification / hours`: `CSR-VEL-01` r2 and `QP-15` r1 both say `24`.

Expected: `agreed`. The superseded `CSR-VEL-01` r1 (`48`) must not interfere.

## Case `unknown`: nothing is asserted

* `heat_treat_furnace / max_temp_c`: no document mentions the subject.
* `final_inspection / paint_color`: the subject exists, the predicate does not.

Expected: `unknown`.

## Case `chain`: a three-revision chain where only the newest counts

* `QP-07` (r1, r2, r3): `record_retention` is `2 years`, `3 years`, `5 years`.
* `QP-18` (r1, r2, r3): `on_site_notice_days` is `30`, `14`, `7`.

Expected: `agreed` with the value from r3 only. `revision_history("QP-07-r3")` lists r2 then r1.

## Cases where supersession and effective dates disagree

In the cases above, a newer revision is always also newer by date, so "newest date wins" and "follow
`SUPERSEDES`" give the same answer. Real document metadata is not that tidy. The next three cases
are about dates that are missing or wrong, or about a requirement a new revision drops. They test
whether the answer comes from the revision chain, not from dates. Each has two questions.

## Case `missing_date`: the newest revision has no effective date

* `WI-31` r2 supersedes r1, but its effective date was left blank. `preheat_minutes` goes from `20`
  to `30` and `max_basket_kg` from `250` to `300`.

Expected: `agreed` with the r2 value. The date is blank, so a date-based method sorts r2 first
(oldest) and returns the superseded r1 value.

## Case `date_error`: an old revision has a wrong date that sorts it as the newest

* `QP-22` r1 has the effective date `2052-01-15` (a transposed `2025`). r2, dated `2025-09-01`,
  supersedes it. `head_bolt_torque` goes from `45 Nm` to `48 Nm` and `cover_bolt_torque` from
  `22 Nm` to `24 Nm`.

Expected: `agreed` with the r2 value. A date-based method trusts the typo and returns the
superseded r1 value.

## Case `withdrawn`: the newest revision drops a requirement

* `WI-33` r2 no longer states `retest_allowed` (r1: `once after reseating`).
* `QP-22` r2 no longer states `thread_locker` (r1: `required`).

Expected: `unknown`. The data model treats a revision as replacing the whole previous one, so a fact
that is not restated is not in force. This is a modelling choice: Supersede cannot tell a
deliberately withdrawn requirement from one the author forgot to carry over (see AUDIT.md).

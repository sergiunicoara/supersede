import json
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "eval"))

from run_extraction_eval import _norm, _store  # noqa: E402
from supersede.extract import load_vocabulary  # noqa: E402
from supersede.ingest import document_files, parse, split_document  # noqa: E402

REAL = ROOT / "examples" / "real"
FILES = document_files(REAL)
GOLD = json.loads((REAL / "gold.json").read_text(encoding="utf-8"))
VOCAB = load_vocabulary(REAL / "vocabulary.json")


def real_store():
    revs = [parse(p.read_text(encoding="utf-8"), p.name) for p in FILES]
    return _store(revs, GOLD)


def test_the_real_folder_is_complete_and_attributed():
    assert len(FILES) == 16 and set(GOLD) == {p.name for p in FILES}
    for p in FILES:
        text = p.read_text(encoding="utf-8")
        assert ("https://www.ecfr.gov" in text or "https://www.fda.gov" in text) and "public domain" in text  # provenance
        # federal regulations are authority 4; the one FDA guidance document (non-binding) is 2
        assert parse(text, p.name).authority == (2 if p.name.startswith("FDA-") else 4)


def test_gold_values_are_verbatim_in_the_real_text():
    for p in FILES:
        _, body = split_document(p.read_text(encoding="utf-8"), p.name)
        body = _norm(body)
        for key, value in GOLD[p.name].items():
            assert key in VOCAB and _norm(value) in body, (p.name, key, value)


def test_real_effective_dates_are_clean_and_the_chain_is_in_order():
    s = real_store()
    assert s.date_warnings() == []
    assert s.history("FAR-13.000-r3") == ["FAR-13.000-r2", "FAR-13.000-r1"]
    assert s.history("CFR21-820-scope-r3") == ["CFR21-820-scope-r2", "CFR21-820-scope-r1"]
    assert s.current_revisions() == ["CFR21-803-18-r2", "CFR21-820-complaints-r2", "CFR21-820-records-r2",
                                     "CFR21-820-scope-r3", "FAR-13.000-r3", "FAR-3.1004-r3", "FDA-MDR-guidance-r1"]


@pytest.mark.parametrize("subject, predicate, day, status, value, source", [
    ("ethics_clause", "value_threshold", None, "agreed", "$7.5 million", "FAR-3.1004-r3"),
    ("ethics_clause", "value_threshold", "2025-10-01", "agreed", "$7.5 million", "FAR-3.1004-r3"),
    ("ethics_clause", "value_threshold", "2025-09-30", "agreed", "$6 million", "FAR-3.1004-r2"),
    ("ethics_clause", "value_threshold", "2018-06-01", "agreed", "$5.5 million", "FAR-3.1004-r1"),
    ("ethics_clause", "value_threshold", "2016-12-31", "unknown", None, None),
    ("simplified_acquisition", "commercial_ceiling", None, "agreed", "$9 million", "FAR-13.000-r3"),
    ("simplified_acquisition", "commercial_ceiling", "2022-03-01", "agreed", "$7.5 million", "FAR-13.000-r2"),
    ("simplified_acquisition", "special_ceiling", "2019-01-01", "agreed", "$13 million", "FAR-13.000-r1"),
    ("simplified_acquisition", "special_ceiling", "2021-01-01", "agreed", "$15 million", "FAR-13.000-r2"),
])
def test_real_history_answers_for_today_and_for_past_dates(subject, predicate, day, status, value, source):
    a = real_store().answer(subject, predicate, as_of=day)
    assert a["status"] == status
    if value is not None:
        assert a["value"] == value and a["sources"] == [source]


def test_an_unchanged_requirement_stays_the_same_across_all_revisions():
    s = real_store()
    for day in ("2017-01-01", "2020-10-02", "2025-10-01", None):
        a = s.answer("ethics_clause", "performance_period", as_of=day)
        assert (a["status"], a["value"]) == ("agreed", "120 days")


# -- quality manufacturing: 21 CFR Part 820 (FDA medical-device quality regulation) -----------------------------
@pytest.mark.parametrize("subject, predicate, day, status, value", [
    # record retention: stated in 820.180 (2016), not stated in 820.35 (2026), where it moved to an incorporated standard
    ("device_records", "minimum_retention", "2020-01-01", "agreed", "2 years"),
    ("device_records", "minimum_retention", "2026-02-03", "agreed", "2 years"),
    ("device_records", "minimum_retention", "2026-02-04", "unknown", None),
    ("device_records", "minimum_retention", None, "unknown", None),
    ("device_records", "minimum_retention", "2016-12-29", "unknown", None),
    # complaint records: the 2016 investigation record had to include the dates and results
    ("complaint_record", "investigation_content", "2018-01-01", "agreed", "dates and results of the investigation"),
    ("complaint_record", "investigation_content", None, "unknown", None),
    # the regulation renames itself
    ("regulation_name", "scope_title", "2019-06-01", "agreed", "quality system regulation"),
    ("regulation_name", "scope_title", "2021-01-01", "agreed", "quality system regulation"),
    ("regulation_name", "scope_title", None, "agreed", "quality management system regulation (QMSR)"),
])
def test_21_cfr_820_history(subject, predicate, day, status, value):
    a = real_store().answer(subject, predicate, as_of=day)
    assert a["status"] == status
    if value is not None:
        assert a["value"] == value


def test_a_requirement_that_leaves_the_text_is_unknown_not_carried_forward():
    """The 2026 text points to ISO 13485 (copyrighted, not in the CFR text), so the CFR no longer states the period."""
    a = real_store().answer("device_records", "minimum_retention")
    assert a == {"status": "unknown", "reason": "no current fact asserted"}


# -- a real authority hierarchy: regulation (4) over non-binding FDA guidance (2) ------------------------------
def test_the_guidance_is_flagged_as_written_from_text_that_was_replaced():
    stale = real_store().stale_derivations()
    assert [(x["revision"], x["source"], x["replaced_by"]) for x in stale] == [
        ("FDA-MDR-guidance-r1", "CFR21-803-18-r1", ["CFR21-803-18-r2"]),
        ("FDA-MDR-guidance-r1", "CFR21-820-complaints-r1", ["CFR21-820-complaints-r2"]),
    ]


def test_today_the_regulation_overrules_the_stale_guidance():
    a = real_store().answer("complaint_handling", "requirement_source")
    assert (a["status"], a["value"], a["source"]) == ("resolved", "Clause 8.2.2 in ISO 13485", "CFR21-820-complaints-r2")
    assert [(o["value"], o["rev"]) for o in a["overruled"]] == [("21 CFR 820.198", "FDA-MDR-guidance-r1")]
    assert "authority 4" in a["reason"]


def test_before_the_rule_changed_the_guidance_was_the_only_statement_in_force():
    s = real_store()
    for day in ("2016-11-08", "2020-01-01", "2026-02-03"):
        a = s.answer("complaint_handling", "requirement_source", as_of=day)
        assert (a["status"], a["value"], a["sources"]) == ("agreed", "21 CFR 820.198", ["FDA-MDR-guidance-r1"]), day
    assert s.answer("complaint_handling", "requirement_source", as_of="2016-11-07")["status"] == "unknown"


@pytest.mark.parametrize("day, value", [(None, "quality management system requirements"), ("2020-01-01", "quality system requirements")])
def test_the_regulation_wording_wins_over_the_guidance_at_each_date(day, value):
    a = real_store().answer("mdr_evaluation", "part_820_reference", as_of=day)
    assert (a["status"], a["value"]) == ("resolved", value)
    assert [o["value"] for o in a["overruled"]] == ["complaint file requirements"]


def test_same_requirement_in_different_words_is_resolved_not_agreed_a_known_limit():
    """The regulation says '2 years' and the guidance 'two years'. Values are compared as strings, so this is a
    contradiction settled by authority (the right answer), not agreement: value normalisation is future work."""
    a = real_store().answer("mdr_event_file", "minimum_retention")
    assert (a["status"], a["value"]) == ("resolved", "2 years")
    assert [o["value"] for o in a["overruled"]] == ["two years"]

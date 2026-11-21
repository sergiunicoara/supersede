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
    assert len(FILES) == 6 and set(GOLD) == {p.name for p in FILES}
    for p in FILES:
        text = p.read_text(encoding="utf-8")
        assert "https://www.ecfr.gov" in text and "public domain" in text  # provenance on every file
        assert parse(text, p.name).authority == 4


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
    assert s.current_revisions() == ["FAR-13.000-r3", "FAR-3.1004-r3"]


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

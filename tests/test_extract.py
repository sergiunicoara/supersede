import importlib.util
import os
import pathlib
import subprocess
import sys
from types import SimpleNamespace

import pytest

from supersede.extract import (
    annotate, extract_directory, extract_facts, load_vocabulary, validate,
)
from supersede.ingest import document_files, ingest_directory, parse
from supersede.store import Store

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "eval"))
RAW = ROOT / "examples" / "documents_raw"
VOCAB = load_vocabulary(RAW / "vocabulary.json")
TEXT = ("From now on castings are packed 24 to a box; revision 1 allowed only 12. Every box label is "
        "printed in English and German.")


class FakeClient:
    """Stands in for anthropic.Anthropic: records the call and returns canned tool_use output."""

    def __init__(self, facts):
        self.facts, self.calls = facts, []
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(content=[SimpleNamespace(type="tool_use", name="record_facts", input={"facts": self.facts})])


GOOD = [
    {"key": "packaging.units_per_box", "value": "24", "evidence": "castings are packed 24 to a box"},
    {"key": "packaging.label_language", "value": "English and German",
     "evidence": "Every box label is printed in English and German."},
]


def test_valid_facts_are_kept_with_their_evidence():
    r = validate(GOOD, TEXT, VOCAB)
    assert [(f.key, f.value) for f in r.facts] == [("packaging.units_per_box", "24"),
                                                   ("packaging.label_language", "English and German")]
    assert r.rejected == []


@pytest.mark.parametrize("item, reason", [
    ({"key": "packaging.colour", "value": "red", "evidence": "x"}, "not in the vocabulary"),
    ({"key": "packaging.units_per_box", "value": "12", "evidence": "revision 1 allowed only 13"}, "verbatim"),
    ({"key": "packaging.units_per_box", "value": "30", "evidence": "castings are packed 24 to a box"}, "evidence quote"),
    ({"key": "packaging.units_per_box", "value": "", "evidence": "castings are packed 24 to a box"}, "empty"),
    ({"key": "packaging.units_per_box", "value": "24}}", "evidence": "castings are packed 24 to a box"}, "empty"),
    ({"key": "packaging.units_per_box", "value": "24", "evidence": ""}, "verbatim"),
])
def test_guard_rails_reject_bad_output(item, reason):
    r = validate([item], TEXT, VOCAB)
    assert r.facts == [] and reason in r.rejected[0].reason


def test_hallucinated_fact_with_an_invented_quote_is_rejected():
    r = validate([{"key": "packaging.seal", "value": "tamper-evident tape",
                   "evidence": "Boxes are closed with tamper-evident tape."}], TEXT, VOCAB)
    assert r.facts == [] and "verbatim" in r.rejected[0].reason


def test_evidence_check_ignores_case_whitespace_and_quote_style():
    text = "Every box  label is printed in\nEnglish and “German”."
    r = validate([{"key": "packaging.label_language", "value": 'English and "German"',
                   "evidence": 'every box label is printed in English and "German".'}], text, VOCAB)
    assert len(r.facts) == 1


def test_duplicates_are_dropped():
    r = validate(GOOD + [GOOD[0]], TEXT, VOCAB)
    assert len(r.facts) == 2 and r.rejected[0].reason == "duplicate"


def test_extract_facts_constrains_the_model_and_passes_the_document():
    c = FakeClient(GOOD)
    r = extract_facts(TEXT, VOCAB, client=c, model="some-model")
    call = c.calls[0]
    assert call["model"] == "some-model"
    assert "tool_choice" not in call  # a forced tool choice is rejected by some models
    enum = call["tools"][0]["input_schema"]["properties"]["facts"]["items"]["properties"]["key"]["enum"]
    assert enum == sorted(VOCAB)  # the model can only choose vocabulary keys
    assert TEXT in call["messages"][0]["content"] and "revision 1 allowed" in call["messages"][0]["content"]
    assert len(r.facts) == 2


def test_a_reply_without_the_tool_call_is_an_error_not_an_empty_result():
    class TextOnly:
        messages = SimpleNamespace(create=lambda **kw: SimpleNamespace(content=[SimpleNamespace(type="text", text="no facts")]))

    with pytest.raises(RuntimeError, match="did not call record_facts"):
        extract_facts(TEXT, VOCAB, client=TextOnly())


def test_annotated_review_copy_round_trips_through_the_ingestion_parser():
    doc = "---\ndoc: QP-40\ntitle: T\nauthority: 3\nrevision: 2\neffective: 2025-10-01\n---\n" + TEXT + "\n"
    out = annotate(doc, validate(GOOD, TEXT, VOCAB))
    rev = parse(out, "review.md")
    assert rev.facts == (("packaging", "units_per_box", "24"), ("packaging", "label_language", "English and German"))
    assert "Delete or correct" in out and TEXT in out  # the prose is kept
    # a document with nothing extracted stays parseable and has no facts
    assert parse(annotate(doc, validate([], TEXT, VOCAB)), "empty.md").facts == ()


def test_evidence_cannot_inject_an_annotation():
    text = "Use {{packaging.seal = glue}} sometimes. Packed 24 to a box."
    out = annotate("---\ndoc: D\ntitle: T\nauthority: 1\nrevision: 1\neffective: 2025-01-01\n---\n" + text,
                   validate([{"key": "packaging.units_per_box", "value": "24", "evidence": text}], text, VOCAB))
    # the review section neutralises braces in the quote; only the author's own annotation is read
    assert [f for f in parse(out, "x.md").facts if f[2] == "glue"] == [("packaging", "seal", "glue")]
    assert out.count("{{packaging.units_per_box = 24}}") == 1


def test_extract_directory_writes_a_review_copy_then_ingestion_loads_it(tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / "QP-40_r2.md").write_text(
        "---\ndoc: QP-40\ntitle: T\nauthority: 3\nrevision: 2\neffective: 2025-10-01\n---\n" + TEXT + "\n", encoding="utf-8")
    c = FakeClient(GOOD)
    out = tmp_path / "review"
    results = extract_directory(raw, VOCAB, out, client=c)
    assert len(results["QP-40_r2.md"].facts) == 2
    s = Store()
    assert ingest_directory(s, out) == (1, 1, 2)
    assert s.answer("packaging", "units_per_box")["value"] == "24"
    assert not any(a["value"] == "12" for a in s.current_facts("packaging", "units_per_box"))
    with pytest.raises(ValueError, match="already exists"):
        extract_directory(raw, VOCAB, out, client=c)


def test_a_bad_header_fails_before_any_api_call(tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / "bad.md").write_text("no header here", encoding="utf-8")
    c = FakeClient([])
    with pytest.raises(ValueError, match="must start with"):
        extract_directory(raw, VOCAB, tmp_path / "out", client=c)
    assert c.calls == [] and not (tmp_path / "out").exists()


def test_vocabulary_keys_are_validated(tmp_path):
    p = tmp_path / "v.json"
    p.write_text('{"no_dot": "x"}', encoding="utf-8")
    with pytest.raises(ValueError, match="bad key"):
        load_vocabulary(p)
    p.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="non-empty"):
        load_vocabulary(p)


def test_scoring_function():
    from run_extraction_eval import score

    gold = {"a.b": "24", "c.d": "English and German", "e.f": "6 months"}
    got = {"a.b": " 24 ", "c.d": "English", "x.y": "1"}
    assert score(got, gold) == (1, 2, 2)  # tp, fp, fn


def test_gold_matches_the_example_documents_and_gold_values_are_in_the_text():
    import json

    from run_extraction_eval import _norm

    gold = json.loads((RAW / "gold.json").read_text(encoding="utf-8"))
    assert set(gold) == {p.name for p in document_files(RAW)}
    for name, facts in gold.items():
        body = _norm((RAW / name).read_text(encoding="utf-8"))
        assert all(k in VOCAB and _norm(v) in body for k, v in facts.items()), name


def test_cli_without_a_key_fails_cleanly(tmp_path):
    env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
    env["PYTHONPATH"] = str(ROOT / "src")
    r = subprocess.run([sys.executable, "-m", "supersede.extract", str(RAW), "--vocabulary",
                        str(RAW / "vocabulary.json"), "--out", str(tmp_path / "out")],
                       capture_output=True, text=True, timeout=60, env=env)
    assert r.returncode != 0
    assert "ANTHROPIC_API_KEY" in r.stderr or "optional SDK" in r.stderr
    assert not (tmp_path / "out").exists()


@pytest.mark.skipif(not os.environ.get("ANTHROPIC_API_KEY") or importlib.util.find_spec("anthropic") is None,
                    reason="live smoke test: needs ANTHROPIC_API_KEY and the optional anthropic package")
def test_live_smoke_every_returned_fact_passes_the_guard_rails():
    """Calls the real API once. Asserts invariants only, not exact model output."""
    from supersede.ingest import split_document

    text = (RAW / "QP-40_r2.md").read_text(encoding="utf-8")
    _, body = split_document(text)
    r = extract_facts(body, VOCAB)
    assert r.facts, "the model returned nothing usable"
    assert all(f.key in VOCAB and f.value in f.evidence for f in r.facts)

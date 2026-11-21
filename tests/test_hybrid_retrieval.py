"""Hybrid retrieval: Relate full-text + vector indexes fused by reciprocal rank."""
import pathlib
import sys

import pytest

from supersede.embed import HashingEmbedder, content_words
from supersede.store import Store

ROOT = pathlib.Path(__file__).resolve().parents[1]
for sub in ("examples", "eval"):
    sys.path.insert(0, str(ROOT / sub))

import run_eval  # noqa: E402
from load_corpus import load_docs, read_corpus, read_topics  # noqa: E402

STORE = ROOT / "examples" / "store" / "supersede-demo.relate"


def small() -> Store:
    s = Store()
    s.add_topic("gauge_calibration", "interval", "How often gauges are recalibrated, the calibration interval")
    s.add_topic("retained_sample", "retention_period", "How long retained samples are kept")
    return s


def test_embedder_is_deterministic_and_normalised():
    e = HashingEmbedder()
    a, b = e.embed("gauge calibration interval"), e.embed("gauge calibration interval")
    assert a == b and len(a) == e.dim
    assert abs(sum(x * x for x in a) - 1.0) < 1e-9
    assert e.embed("the of and") is None  # only stop words
    assert content_words("How MANY parts?") == ["parts"]


def test_vector_finds_a_word_form():
    s = small()
    try:
        got = s.ask("How often do we calibrate a gauge?", retrieval="vector")
        assert got["matched"]["subject"] == "gauge_calibration"
        assert got["matched"]["via"]["vector_score"] >= Store.MIN_VECTOR_SCORE
    finally:
        s.close()


def test_off_topic_is_rejected_in_every_mode():
    s = small()
    try:
        for mode in ("fulltext", "vector", "hybrid"):
            assert s.ask("What time does the cafeteria open?", retrieval=mode)["status"] == "no_match", mode
    finally:
        s.close()


def test_hybrid_reports_how_it_matched():
    s = small()
    try:
        via = s.ask("How long are retained samples kept?")["matched"]["via"]
        assert via["mode"] == "hybrid" and via["fulltext_rank"] == 1 and via["vector_score"] is not None
    finally:
        s.close()


def test_unknown_mode_is_an_error():
    s = small()
    try:
        with pytest.raises(ValueError, match="retrieval"):
            s.ask("anything", retrieval="magic")
    finally:
        s.close()


def test_a_store_built_with_another_embedder_falls_back_to_full_text():
    class Other:
        name, dim = "other-v1", 8

        def embed(self, text):
            return [1.0] + [0.0] * 7

    s = Store(embedder=Other())
    try:
        s.add_topic("gauge_calibration", "interval", "How often gauges are recalibrated")
        s._embedder = HashingEmbedder()  # a reader opens it with a different embedder
        got = s.ask("How often are gauges recalibrated?")
        assert got["matched"]["subject"] == "gauge_calibration"
        assert got["matched"]["via"]["vector_score"] is None  # vectors ignored, full-text answered
    finally:
        s.close()


def test_committed_store_has_both_indexes_and_answers_read_only():
    s = Store(str(STORE), read_only=True)
    try:
        got = s.ask("What time limit applies for notifying customers?")
        assert got["matched"]["via"]["mode"] == "hybrid"
        assert s.ask("What is the lunch menu in the cafeteria?")["status"] == "no_match"
    finally:
        s.close()


def test_retrieval_comparison_hybrid_is_never_worse_than_full_text_on_the_original_questions():
    ft = run_eval.evaluate_retrieval(mode="fulltext")
    hy = run_eval.evaluate_retrieval(mode="hybrid")
    assert sum(x["ok"] for x in hy) >= sum(x["ok"] for x in ft)
    assert sum(x["ok"] for x in hy) == len(hy) == 23
    variants = run_eval.evaluate_retrieval(section="retrieval_variants", mode="hybrid")
    assert len(variants) == 18
    assert sum(x["ok"] for x in variants) >= sum(x["ok"] for x in run_eval.evaluate_retrieval(
        section="retrieval_variants", mode="fulltext"))

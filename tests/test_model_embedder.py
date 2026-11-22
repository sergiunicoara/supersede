"""The optional trained embedding model. Skipped unless `pip install fastembed` (the model downloads on first use)."""
import pathlib
import sys

import pytest

pytest.importorskip("fastembed")

from supersede.embed_model import FastEmbedEmbedder  # noqa: E402
from supersede.store import Store  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "examples"))
from load_corpus import CORPUS_DIR, load_docs, read_corpus, read_topics  # noqa: E402


@pytest.fixture(scope="module")
def store():
    s = Store(embedder=FastEmbedEmbedder())
    load_docs(s, read_corpus(CORPUS_DIR), read_topics(CORPUS_DIR))
    yield s
    s.close()


def test_a_synonym_finds_the_right_topic(store):
    # "hardened" shares no word with "cure": the hashing embedder's hybrid answers this with the wrong topic
    got = store.ask("How many minutes until the coating has hardened?", retrieval="vector")
    assert got["matched"]["subject"] == "paint_line" and got["matched"]["predicate"] == "cure_time_min"
    assert got["answer"]["value"] == "35"


def test_off_topic_is_still_rejected(store):
    assert store.ask("Where is the nearest first-aid kit?", retrieval="vector")["status"] == "no_match"


def test_the_threshold_comes_from_calibration_not_from_the_default(store):
    assert store._min_vector_score() == 0.85 != Store.MIN_VECTOR_SCORE

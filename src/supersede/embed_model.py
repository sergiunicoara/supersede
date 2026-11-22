"""Optional: a trained embedding model for Relate's vector index (so synonyms work).

    pip install "supersede[embed]"          # adds fastembed (ONNX runtime, no PyTorch)
    from supersede.embed_model import FastEmbedEmbedder
    store = Store(path, embedder=FastEmbedEmbedder())

The default `HashingEmbedder` needs nothing but matches word forms and typos only. This embedder runs a small
sentence-embedding model locally (default `BAAI/bge-small-en-v1.5`, 384 dimensions), downloaded on first use from the
Hugging Face hub by fastembed. Nothing is sent anywhere at query time. A store remembers which embedder built its
vectors, and falls back to full-text search if it is opened with a different one, so build the store and query it with
the same embedder.

`min_score` is the vector score (Relate reports (1 + cosine) / 2) below which a hit is ignored; it is chosen for this
model on eval/calibration.yaml by `python eval/calibrate_vector.py --embedder model`, not on the evaluation questions.
"""
from __future__ import annotations


class FastEmbedEmbedder:
    def __init__(self, model: str = "BAAI/bge-small-en-v1.5", dim: int = 384, min_score: float | None = None) -> None:
        try:
            from fastembed import TextEmbedding
        except ImportError as exc:  # pragma: no cover - exercised only without the extra
            raise ImportError('FastEmbedEmbedder needs the optional extra: pip install "supersede[embed]"') from exc
        self._model = TextEmbedding(model_name=model)
        self.dim = dim
        self.name = f"fastembed-{model}"
        if min_score is not None:
            self.min_score = min_score
        elif model in DEFAULT_MIN_SCORE:
            self.min_score = DEFAULT_MIN_SCORE[model]

    def embed(self, text: str) -> list[float] | None:
        if not text.strip():
            return None
        vec = next(iter(self._model.embed([text])))
        return [float(x) for x in vec]


# Chosen on eval/calibration.yaml (see the module docstring); filled in after calibration.
DEFAULT_MIN_SCORE: dict[str, float] = {"BAAI/bge-small-en-v1.5": 0.85}  # plateau 0.83-0.87 on the calibration set

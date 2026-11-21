"""Embeddings for Relate's vector index, with no model and no dependency.

Relate stores and searches vectors but does not compute them. The default `HashingEmbedder` turns text into a
fixed-size vector by hashing its words and the character 3-grams inside each word (signed feature hashing, then
L2-normalised). It is deterministic (CRC32, not Python's randomised `hash`), so a vector computed today matches one
computed on another machine.

What it is good at: word forms and typos (`retaining` is close to `retention`, `torqued` to `torque`), because
related forms share character n-grams. What it is NOT: it has no idea that `bake` means `cure`. For real synonyms
pass an embedder backed by a trained model, anything with `name`, `dim` and `embed(text)`; the store records the
embedder's name and falls back to full-text search if it is later opened with a different one.
"""
from __future__ import annotations

import math
import re
import zlib
from typing import Protocol

STOPWORDS = frozenset(
    "a an and are as at be but by can do does for from had has have how i if in into is it its many may much "
    "me my no not of on or our shall should so than that the their then there these they this to "
    "us was we were what when where which who why will with would you your".split())


def content_words(text: str) -> list[str]:
    """Lower-case alphanumeric words of `text` without stop words."""
    return [w for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in STOPWORDS]


class Embedder(Protocol):
    name: str
    dim: int

    def embed(self, text: str) -> list[float] | None:
        """A vector of length `dim`, or None if the text has nothing to embed."""


class HashingEmbedder:
    """Signed feature hashing of words and in-word character 3-grams."""

    def __init__(self, dim: int = 256, word_weight: float = 1.0, ngram_weight: float = 0.5) -> None:
        self.dim, self._ww, self._gw = dim, word_weight, ngram_weight
        self.name = f"hash-ngram-{dim}-v1"

    def _add(self, vec: list[float], feature: str, weight: float) -> None:
        raw = feature.encode("utf-8")
        sign = 1.0 if zlib.crc32(b"s" + raw) & 1 else -1.0
        vec[zlib.crc32(raw) % self.dim] += sign * weight

    def embed(self, text: str) -> list[float] | None:
        words = content_words(text)
        if not words:
            return None
        vec = [0.0] * self.dim
        for w in words:
            self._add(vec, "w:" + w, self._ww)
            padded = f"^{w}$"
            for i in range(len(padded) - 2):
                self._add(vec, "g:" + padded[i:i + 3], self._gw)
        norm = math.sqrt(sum(v * v for v in vec))
        return [v / norm for v in vec] if norm else None

"""Local sentence embeddings, on CPU, inside the job.

PLAN.md section 2.3: story clustering and the first ranking feature both need a vector per
item, and both run on CPU in the Cloud Run job. No embedding call ever leaves the machine,
which is most of why a digest costs cents.

Two backends behind one protocol. `FastEmbed` is bge-small through ONNX, which is what
production uses. `Hashing` is a deterministic bag-of-words projection that needs no model
download: it is what the test suite and CI use, and what a first run on a new machine falls
back to, so nothing in the pipeline is untestable because a model is missing.
"""

from __future__ import annotations

import hashlib
import math
import re
from collections.abc import Sequence
from typing import Protocol

# bge-small-en-v1.5: 384 dimensions, about 130 MB, and the smallest model that ranks well
# on retrieval benchmarks. The hashing backend matches its width so the two are swappable.
MODEL_NAME = "BAAI/bge-small-en-v1.5"
DIMENSIONS = 384

WORD = re.compile(r"[a-z0-9]+")

Vector = tuple[float, ...]

# Texts embedded per ONNX call. fastembed's default is 256, and a story text runs to the
# model's 512-token limit, so a batch's attention matrices alone are gigabytes: measured
# 2026-10-08, 120 long texts peaked at 2.5 GB resident at 256 and 0.86 GB at 16. The daily
# job was killed for memory at 2 GiB on its second audience. Throughput barely changes on
# one CPU, which is what the job has.
BATCH_SIZE = 16


class Embedder(Protocol):
    """Turns text into unit-length vectors."""

    dimensions: int

    def embed(self, texts: Sequence[str]) -> list[Vector]: ...


def normalise(values: list[float]) -> Vector:
    """Unit length, so cosine similarity is a dot product."""
    magnitude = math.sqrt(sum(value * value for value in values))
    if magnitude == 0.0:
        return tuple(values)
    return tuple(value / magnitude for value in values)


def cosine(left: Vector, right: Vector) -> float:
    """Cosine similarity of two unit vectors."""
    return sum(a * b for a, b in zip(left, right, strict=True))


class Hashing:
    """A deterministic hashed bag of words.

    Not a pretence at semantics: it captures word overlap and nothing more, which is enough
    to exercise every code path that consumes a vector. Tests that care about meaning use
    fixtures with overlapping wording, and the numbers this project publishes come from a
    run with the real model, recorded as such.
    """

    def __init__(self, dimensions: int = DIMENSIONS) -> None:
        self.dimensions = dimensions

    def embed(self, texts: Sequence[str]) -> list[Vector]:
        vectors: list[Vector] = []
        for text in texts:
            values = [0.0] * self.dimensions
            for word in WORD.findall(text.lower()):
                digest = hashlib.blake2b(word.encode("utf-8"), digest_size=8).digest()
                index = int.from_bytes(digest[:4], "big") % self.dimensions
                # The second half of the digest picks the sign, so unrelated words cancel
                # rather than always adding.
                sign = 1.0 if digest[4] % 2 == 0 else -1.0
                values[index] += sign
            vectors.append(normalise(values))
        return vectors


class FastEmbed:
    """bge-small through ONNX runtime. Production, and behind the `embed` extra."""

    def __init__(self, model_name: str = MODEL_NAME, cache_dir: str | None = None) -> None:
        from fastembed import TextEmbedding  # imported here: the `embed` extra is optional

        self.dimensions = DIMENSIONS
        self._model = TextEmbedding(model_name=model_name, cache_dir=cache_dir)

    def embed(self, texts: Sequence[str]) -> list[Vector]:
        if not texts:
            return []
        return [
            normalise([float(value) for value in vector])
            for vector in self._model.embed(list(texts), batch_size=BATCH_SIZE)
        ]


def default_embedder(prefer_model: bool = True) -> Embedder:
    """The real model where it is installed, the hashing backend where it is not.

    The fallback is reported by `clippings run`, never silent: a digest produced with the
    hashing backend has worse clusters, and a measured number must say which was used.
    """
    if prefer_model:
        try:
            return FastEmbed()
        except Exception:
            return Hashing()
    return Hashing()


def backend_name(embedder: Embedder) -> str:
    """What to record next to a number produced with this embedder."""
    return (
        f"{type(embedder).__name__.lower()}:{MODEL_NAME}"
        if isinstance(embedder, FastEmbed)
        else "hashing"
    )

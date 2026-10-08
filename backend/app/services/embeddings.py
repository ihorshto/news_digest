"""Local sentence embeddings (fastembed, multilingual) and vector helpers."""

import hashlib
import logging
import re
from typing import Protocol

import numpy as np

logger = logging.getLogger(__name__)


class Embedder(Protocol):
    def embed(self, texts: list[str]) -> np.ndarray:
        """Return an (n, dim) float32 array of L2-normalized vectors."""
        ...


def _normalize(matrix: np.ndarray) -> np.ndarray:
    matrix = np.asarray(matrix, dtype=np.float32)
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return matrix / norms


class FastEmbedder:
    def __init__(self, model_name: str, cache_dir: str | None = None):
        from fastembed import TextEmbedding

        logger.info("loading embedding model %s (cache: %s)", model_name, cache_dir)
        self._model = TextEmbedding(model_name=model_name, cache_dir=cache_dir)

    def embed(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, 0), dtype=np.float32)
        return _normalize(np.array(list(self._model.embed(texts, batch_size=32))))


class HashEmbedder:
    """Deterministic bag-of-words embedder for tests (no model download)."""

    def __init__(self, dim: int = 256):
        self.dim = dim

    def embed(self, texts: list[str]) -> np.ndarray:
        out = np.zeros((len(texts), self.dim), dtype=np.float32)
        for row, text in enumerate(texts):
            for token in re.findall(r"\w+", text.lower()):
                if len(token) < 3:
                    continue
                digest = hashlib.md5(token[:6].encode()).digest()
                out[row, int.from_bytes(digest[:4], "little") % self.dim] += 1.0
        return _normalize(out)


def to_bytes(vector: np.ndarray) -> bytes:
    return np.asarray(vector, dtype=np.float32).tobytes()


def from_bytes(blob: bytes) -> np.ndarray:
    return np.frombuffer(blob, dtype=np.float32)


def article_text(title: str, snippet: str | None) -> str:
    return f"{title}. {snippet}" if snippet else title


def get_embedder(settings) -> Embedder:
    if settings.fake_embeddings:
        logger.warning("FAKE_EMBEDDINGS=1: using the hash embedder (tests/dev only)")
        return HashEmbedder()
    return FastEmbedder(settings.embedding_model, settings.embedding_cache_dir)

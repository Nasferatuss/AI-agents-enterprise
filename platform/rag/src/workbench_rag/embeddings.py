"""Embedding backends.

Production path is Ollama on the GPU box (ADR-003/ADR-008: embeddings run
locally — nomic-embed-text / bge / e5). HashEmbedder is a deterministic
bag-of-words fallback for tests and keyless dev: same text → same vector,
shared words → cosine similarity. It is NOT semantic.
"""

import hashlib
import math
import re
from typing import Protocol

import httpx


class Embedder(Protocol):
    async def embed(self, texts: list[str]) -> list[list[float]]: ...


class EmbeddingError(Exception):
    pass


class OllamaEmbedder:
    def __init__(self, base_url: str, model: str, http: httpx.AsyncClient | None = None):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self._http = http or httpx.AsyncClient()

    async def embed(self, texts: list[str]) -> list[list[float]]:
        try:
            resp = await self._http.post(
                f"{self.base_url}/api/embed",
                json={"model": self.model, "input": texts},
                timeout=120.0,
            )
        except httpx.HTTPError as exc:
            raise EmbeddingError(f"ollama unreachable at {self.base_url}: {exc}") from exc
        if resp.status_code != 200:
            raise EmbeddingError(f"ollama embed HTTP {resp.status_code}: {resp.text[:200]}")
        embeddings = resp.json().get("embeddings")
        if not embeddings or len(embeddings) != len(texts):
            raise EmbeddingError("ollama embed returned malformed embeddings")
        return embeddings


_WORD_RE = re.compile(r"\w+", re.UNICODE)


class HashEmbedder:
    """Deterministic hashed bag-of-words vectors (tests / keyless dev only)."""

    def __init__(self, dim: int = 256):
        self.dim = dim

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._one(t) for t in texts]

    def _one(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        for word in _WORD_RE.findall(text.lower()):
            h = int.from_bytes(hashlib.md5(word.encode()).digest()[:4], "big")
            vec[h % self.dim] += 1.0
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]

"""RAG pipeline: ingest (chunk → embed → upsert) and hybrid search.

Hybrid = Reciprocal Rank Fusion of dense (Qdrant cosine) and lexical (BM25)
rankings. BM25 runs in-process over the collection's chunks — honest and simple
at demo scale; the interface stays put when it moves to Qdrant sparse vectors.
"""

import re

from rank_bm25 import BM25Okapi

from workbench_rag.chunking import chunk_document
from workbench_rag.embeddings import Embedder
from workbench_rag.store import QdrantStore
from workbench_rag.types import Chunk, Document, IngestStats, ScoredChunk
from workbench_shared.logging import get_logger

log = get_logger(__name__)

_WORD_RE = re.compile(r"\w+", re.UNICODE)
_RRF_K = 60


def _tokenize(text: str) -> list[str]:
    return _WORD_RE.findall(text.lower())


def rrf_fuse(rankings: list[list[Chunk]], top_k: int) -> list[ScoredChunk]:
    scores: dict[str, float] = {}
    by_id: dict[str, Chunk] = {}
    for ranking in rankings:
        for rank, chunk in enumerate(ranking):
            scores[chunk.id] = scores.get(chunk.id, 0.0) + 1.0 / (_RRF_K + rank + 1)
            by_id[chunk.id] = chunk
    ordered = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)[:top_k]
    return [
        ScoredChunk(chunk=by_id[cid], score=score, retrieval="hybrid") for cid, score in ordered
    ]


class RagPipeline:
    def __init__(self, embedder: Embedder, store: QdrantStore):
        self.embedder = embedder
        self.store = store

    async def ingest(self, documents: list[Document]) -> IngestStats:
        chunks: list[Chunk] = []
        for doc in documents:
            chunks += chunk_document(doc)
        if chunks:
            vectors = await self.embedder.embed([c.text for c in chunks])
            await self.store.upsert(chunks, vectors)
        log.info(
            "rag ingest",
            index=self.store.collection,
            documents=len(documents),
            chunks=len(chunks),
        )
        return IngestStats(
            documents=len(documents), chunks=len(chunks), index=self.store.collection
        )

    async def search(self, query: str, top_k: int = 5, hybrid: bool = True) -> list[ScoredChunk]:
        [query_vector] = await self.embedder.embed([query])
        dense = await self.store.search(query_vector, top_k=top_k * 4)
        if not hybrid:
            return dense[:top_k]

        corpus = await self.store.all_chunks()
        if not corpus:
            return []
        bm25 = BM25Okapi([_tokenize(c.text) for c in corpus])
        lexical_scores = bm25.get_scores(_tokenize(query))
        lexical = [
            chunk
            for score, chunk in sorted(
                zip(lexical_scores, corpus, strict=True), key=lambda sc: sc[0], reverse=True
            )
            if score > 0
        ][: top_k * 4]

        results = rrf_fuse([[s.chunk for s in dense], lexical], top_k)
        log.info(
            "rag search",
            index=self.store.collection,
            query_len=len(query),
            dense=len(dense),
            lexical=len(lexical),
            returned=len(results),
        )
        return results

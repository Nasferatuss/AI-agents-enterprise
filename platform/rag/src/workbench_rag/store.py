"""Qdrant-backed chunk store.

Point ids are uuid5 of the chunk id; the chunk itself lives in the payload.
AsyncQdrantClient(":memory:") gives a full in-process store for tests and
Docker-less dev.
"""

import uuid

from qdrant_client import AsyncQdrantClient, models

from workbench_rag.types import Chunk, ScoredChunk

_NS = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")  # uuid.NAMESPACE_DNS


def _point_id(chunk_id: str) -> str:
    return str(uuid.uuid5(_NS, chunk_id))


class QdrantStore:
    def __init__(self, client: AsyncQdrantClient, collection: str):
        self.client = client
        self.collection = collection

    async def ensure_collection(self, dim: int) -> None:
        if not await self.client.collection_exists(self.collection):
            await self.client.create_collection(
                collection_name=self.collection,
                vectors_config=models.VectorParams(size=dim, distance=models.Distance.COSINE),
            )

    async def upsert(self, chunks: list[Chunk], vectors: list[list[float]]) -> None:
        await self.ensure_collection(dim=len(vectors[0]))
        await self.client.upsert(
            collection_name=self.collection,
            points=[
                models.PointStruct(
                    id=_point_id(chunk.id), vector=vector, payload=chunk.model_dump()
                )
                for chunk, vector in zip(chunks, vectors, strict=True)
            ],
        )

    async def search(self, vector: list[float], top_k: int) -> list[ScoredChunk]:
        result = await self.client.query_points(
            collection_name=self.collection, query=vector, limit=top_k, with_payload=True
        )
        return [
            ScoredChunk(chunk=Chunk(**p.payload), score=p.score, retrieval="dense")
            for p in result.points
        ]

    async def all_chunks(self) -> list[Chunk]:
        """Full scan — feeds in-process BM25. Fine at demo scale; replace with
        Qdrant sparse vectors when corpora grow."""
        chunks: list[Chunk] = []
        offset = None
        while True:
            points, offset = await self.client.scroll(
                collection_name=self.collection, limit=256, offset=offset, with_payload=True
            )
            chunks += [Chunk(**p.payload) for p in points]
            if offset is None:
                return chunks

    async def count(self) -> int:
        return (await self.client.count(self.collection)).count

    async def exists(self) -> bool:
        return await self.client.collection_exists(self.collection)

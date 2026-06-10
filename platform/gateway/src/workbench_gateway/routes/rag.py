"""RAG Core endpoints: ingest documents and search indexes."""

from functools import lru_cache

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from qdrant_client import AsyncQdrantClient

from workbench_rag import (
    HashEmbedder,
    IngestStats,
    OllamaEmbedder,
    QdrantStore,
    RagPipeline,
    ScoredChunk,
    from_text,
)
from workbench_rag.embeddings import EmbeddingError
from workbench_shared.config import get_settings

router = APIRouter(prefix="/v1/rag", tags=["rag"])

_COLLECTION_PREFIX = "rag_"


@lru_cache
def _qdrant() -> AsyncQdrantClient:
    return AsyncQdrantClient(url=get_settings().qdrant_url)


def get_pipeline(index: str) -> RagPipeline:
    s = get_settings()
    if s.embeddings_backend == "hash":
        embedder = HashEmbedder()
    else:
        embedder = OllamaEmbedder(base_url=s.local_llm_base_url, model=s.embedding_model)
    return RagPipeline(embedder, QdrantStore(_qdrant(), f"{_COLLECTION_PREFIX}{index}"))


class DocumentIn(BaseModel):
    source: str
    text: str = Field(min_length=1)
    metadata: dict = {}


class IngestRequest(BaseModel):
    documents: list[DocumentIn] = Field(min_length=1)


class SearchRequest(BaseModel):
    query: str = Field(min_length=1)
    top_k: int = Field(default=5, ge=1, le=50)
    hybrid: bool = True


class IndexInfo(BaseModel):
    name: str
    chunks: int


@router.get("/indexes", response_model=list[IndexInfo])
async def list_indexes() -> list[IndexInfo]:
    collections = (await _qdrant().get_collections()).collections
    infos = []
    for c in collections:
        if c.name.startswith(_COLLECTION_PREFIX):
            count = (await _qdrant().count(c.name)).count
            infos.append(IndexInfo(name=c.name.removeprefix(_COLLECTION_PREFIX), chunks=count))
    return infos


@router.post("/indexes/{index}/documents", response_model=IngestStats)
async def ingest(index: str, req: IngestRequest) -> IngestStats:
    docs = [from_text(d.source, d.text, d.metadata) for d in req.documents]
    try:
        return await get_pipeline(index).ingest(docs)
    except EmbeddingError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/indexes/{index}/search", response_model=list[ScoredChunk])
async def search(index: str, req: SearchRequest) -> list[ScoredChunk]:
    pipeline = get_pipeline(index)
    if not await pipeline.store.exists():
        raise HTTPException(status_code=404, detail=f"unknown index: {index}")
    try:
        return await pipeline.search(req.query, top_k=req.top_k, hybrid=req.hybrid)
    except EmbeddingError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

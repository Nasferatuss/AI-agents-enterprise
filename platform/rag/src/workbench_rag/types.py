"""RAG Core types."""

from pydantic import BaseModel, Field


class Document(BaseModel):
    id: str
    source: str  # file path, URL, or logical name
    text: str
    metadata: dict = Field(default_factory=dict)


class Chunk(BaseModel):
    id: str  # "{doc_id}:{ordinal}"
    doc_id: str
    source: str
    ordinal: int
    text: str
    metadata: dict = Field(default_factory=dict)


class ScoredChunk(BaseModel):
    chunk: Chunk
    score: float
    retrieval: str  # "dense" | "bm25" | "hybrid"


class IngestStats(BaseModel):
    documents: int
    chunks: int
    index: str

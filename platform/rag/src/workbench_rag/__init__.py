"""RAG Core: ingestion, chunking, embeddings, hybrid search."""

from workbench_rag.chunking import chunk_document
from workbench_rag.embeddings import HashEmbedder, OllamaEmbedder
from workbench_rag.loaders import from_text, load_path
from workbench_rag.pipeline import RagPipeline
from workbench_rag.store import QdrantStore
from workbench_rag.types import Chunk, Document, IngestStats, ScoredChunk

__all__ = [
    "Chunk",
    "Document",
    "HashEmbedder",
    "IngestStats",
    "OllamaEmbedder",
    "QdrantStore",
    "RagPipeline",
    "ScoredChunk",
    "chunk_document",
    "from_text",
    "load_path",
]

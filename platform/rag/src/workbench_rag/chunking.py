"""Heading-aware chunking with overlap.

Markdown documents are first split at headings so a chunk never straddles a
section boundary, then long sections are packed into ~target_tokens pieces by
paragraph with tail overlap. Token counts use the same chars/4 heuristic as the
Context Engine.
"""

import re

from workbench_rag.types import Chunk, Document

_CHARS_PER_TOKEN = 4
_HEADING_RE = re.compile(r"^#{1,6} ", re.MULTILINE)


def _split_sections(text: str) -> list[str]:
    """Split markdown at headings; the heading stays with its section."""
    starts = [m.start() for m in _HEADING_RE.finditer(text)]
    if not starts:
        return [text]
    bounds = ([0] if starts[0] != 0 else []) + starts + [len(text)]
    return [text[a:b] for a, b in zip(bounds, bounds[1:], strict=False)]


def _split_paragraphs(section: str) -> list[str]:
    return [p for p in (p.strip() for p in section.split("\n\n")) if p]


def chunk_document(
    doc: Document,
    target_tokens: int = 400,
    overlap_tokens: int = 50,
) -> list[Chunk]:
    target_chars = target_tokens * _CHARS_PER_TOKEN
    overlap_chars = overlap_tokens * _CHARS_PER_TOKEN

    pieces: list[str] = []
    for section in _split_sections(doc.text):
        paragraphs = _split_paragraphs(section)
        current = ""
        for para in paragraphs:
            if current and len(current) + len(para) > target_chars:
                pieces.append(current)
                current = current[-overlap_chars:] + "\n\n" if overlap_chars else ""
            current += para + "\n\n"
        if current.strip():
            pieces.append(current)

    return [
        Chunk(
            id=f"{doc.id}:{i}",
            doc_id=doc.id,
            source=doc.source,
            ordinal=i,
            text=piece.strip(),
            metadata=doc.metadata,
        )
        for i, piece in enumerate(pieces)
    ]

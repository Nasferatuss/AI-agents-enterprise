"""Document loaders: markdown/plain text and PDF (pypdf)."""

import hashlib
from pathlib import Path

from pypdf import PdfReader

from workbench_rag.types import Document

_TEXT_SUFFIXES = {".md", ".txt", ".rst"}


def _doc_id(source: str) -> str:
    return hashlib.sha256(source.encode()).hexdigest()[:16]


def load_path(path: str | Path) -> Document:
    p = Path(path)
    if p.suffix.lower() == ".pdf":
        reader = PdfReader(str(p))
        text = "\n\n".join(page.extract_text() or "" for page in reader.pages)
    elif p.suffix.lower() in _TEXT_SUFFIXES:
        text = p.read_text(encoding="utf-8")
    else:
        raise ValueError(f"unsupported file type: {p.suffix} ({p})")
    return Document(id=_doc_id(str(p)), source=str(p), text=text)


def from_text(source: str, text: str, metadata: dict | None = None) -> Document:
    return Document(id=_doc_id(source), source=source, text=text, metadata=metadata or {})

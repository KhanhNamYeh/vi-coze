"""Hợp đồng metadata của một chunk.

Định nghĩa những gì được phép nằm trong `Document.metadata`. Thêm field sau khi
đã index thì phải index lại toàn bộ.
"""

from __future__ import annotations

import hashlib

from pydantic import BaseModel, Field


class ChunkMeta(BaseModel):
    """Metadata gắn vào mỗi chunk."""

    doc_id: str
    section: str | None = None
    table_name: str | None = None
    no: str | None = None
    part: str = "1/1"
    source_path: str | None = None
    n_chars: int = 0
    chunk_id: str = ""
    content_hash: str = ""

    model_config = {"extra": "forbid"}

    @classmethod
    def build(cls, *, text: str, doc_id: str, **kw) -> "ChunkMeta":
        """Tính n_chars, chunk_id, content_hash từ nội dung."""
        meta = cls(doc_id=doc_id, n_chars=len(text), **kw)
        meta.content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
        key = f"{meta.doc_id}|{meta.no}|{meta.part}"
        meta.chunk_id = hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]
        return meta


def context_prefix(doc_title: str, meta: ChunkMeta) -> str:
    """Đường dẫn tiêu đề để prepend vào text trước khi embed."""
    trail = [doc_title, meta.section, meta.table_name]
    return " > ".join(t for t in trail if t)

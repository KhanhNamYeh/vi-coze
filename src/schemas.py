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

    # Đường về IR: phần tử nào của `<doc_id>.extract.json` đã ghép nên chunk này,
    # và chunk trải từ dòng nào tới dòng nào trong `<doc_id>.md`. Có hai thứ này
    # thì trích dẫn nguồn và soi lại chunk hỏng không phải đoán.
    element_ids: list[str] = Field(default_factory=list)
    line_start: int | None = None
    line_end: int | None = None

    n_chars: int = 0
    n_tokens: int | None = None
    chunk_id: str = ""
    content_hash: str = ""

    model_config = {"extra": "forbid"}

    @classmethod
    def build(cls, *, text: str, doc_id: str, **kw) -> "ChunkMeta":
        """Tính n_chars, chunk_id, content_hash từ nội dung.

        `chunk_id` băm NỘI DUNG trong phạm vi một tài liệu, không băm vị trí.
        Băm theo vị trí (`doc_id|no|part`) thì chèn một bảng ở đầu tài liệu là
        đổi ID của mọi chunk phía sau, dù nội dung chúng không đổi - index lại
        thành ghi đè toàn bộ thay vì thêm mới.
        """
        meta = cls(doc_id=doc_id, n_chars=len(text), **kw)
        meta.content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
        scoped = f"{meta.doc_id}|{meta.content_hash}"
        meta.chunk_id = hashlib.sha256(scoped.encode("utf-8")).hexdigest()[:16]
        return meta


    def with_rendered(self, text: str, *, n_tokens: int | None = None) -> "ChunkMeta":
        """Cập nhật số đo theo TEXT THẬT SỰ được lưu.

        `chunk_id` giữ nguyên vì nó định danh *lát cắt nào* của tài liệu; thêm
        breadcrumb hay đổi tiêu đề tài liệu không làm nó thành một chunk khác.
        `content_hash` thì bám `page_content`, để phát hiện nội dung lưu đã đổi.
        """
        return self.model_copy(update={
            "n_chars": len(text),
            "n_tokens": n_tokens,
            "content_hash": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        })


def context_prefix(
    doc_title: str,
    meta: ChunkMeta,
    *,
    separator: str = " > ",
    include_doc_title: bool = True,
) -> str:
    """Đường dẫn tiêu đề để prepend vào text trước khi embed."""
    trail = [doc_title if include_doc_title else None, meta.section, meta.table_name]
    return separator.join(t for t in trail if t)

"""Cross-encoder rerank.

Khác embedding: cross-encoder đọc đồng thời (query, chunk) nên chấm điểm sát
hơn, nhưng phải chạy một lần cho mỗi ứng viên — chỉ dùng ở bước cuối, trên tập
đã thu hẹp.
"""

from __future__ import annotations

from collections.abc import Sequence
from functools import lru_cache

from langchain_classic.retrievers.document_compressors import CrossEncoderReranker
from langchain_core.callbacks import Callbacks
from langchain_core.cross_encoders import BaseCrossEncoder
from langchain_core.documents import Document

from ..config import RERANK_MODEL


class VietnameseReranker(BaseCrossEncoder):
    """BaseCrossEncoder chạy trên sentence-transformers CrossEncoder."""

    def __init__(self, model_name: str = RERANK_MODEL) -> None:
        from sentence_transformers import CrossEncoder

        self.model_name = model_name
        self._model = CrossEncoder(model_name)

    def score(self, text_pairs: list[tuple[str, str]]) -> list[float]:
        return [float(s) for s in self._model.predict(text_pairs)]


@lru_cache(maxsize=1)
def get_reranker() -> VietnameseReranker:
    return VietnameseReranker()


class ScoringReranker(CrossEncoderReranker):
    """Như CrossEncoderReranker nhưng ghi điểm vào `metadata["rerank_score"]`.

    Bản gốc trả về document đã sắp xếp rồi bỏ điểm đi, nên phía gọi không đặt
    được ngưỡng cắt.
    """

    def compress_documents(
        self,
        documents: Sequence[Document],
        query: str,
        callbacks: Callbacks | None = None,
    ) -> Sequence[Document]:
        scores = self.model.score([(query, d.page_content) for d in documents])
        ranked = sorted(zip(documents, scores), key=lambda p: p[1], reverse=True)
        return [
            Document(
                page_content=d.page_content,
                metadata={**d.metadata, "rerank_score": float(s)},
            )
            for d, s in ranked[: self.top_n]
        ]

"""BM25 sparse encoder, dùng chung cho index và query."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from ..config_sql import (
    BM25_B,
    BM25_DISABLE_STEMMER,
    BM25_K,
    SPARSE_MODEL,
)


@dataclass(frozen=True)
class Sparse:
    indices: list[int]
    values: list[float]


@lru_cache(maxsize=1)
def get_sparse_model():
    from fastembed import SparseTextEmbedding

    return SparseTextEmbedding(
        model_name=SPARSE_MODEL,
        k=BM25_K,
        b=BM25_B,
        disable_stemmer=BM25_DISABLE_STEMMER,
    )


def encode_passages(texts: list[str]) -> list[Sparse]:
    """Mã hoá document: trọng số tần suất, không chuẩn hoá độ dài (`b=0`)."""
    return [
        Sparse(indices=e.indices.tolist(), values=e.values.tolist())
        for e in get_sparse_model().embed(texts)
    ]


def encode_query(text: str) -> Sparse:
    """Mã hoá query: chỉ liệt kê term, IDF do Qdrant áp lúc chấm điểm.

    BM25 không đối xứng — dùng `encode_passages` cho query là sai công thức mà
    vẫn chạy, không báo lỗi.
    """
    e = next(iter(get_sparse_model().query_embed(text)))
    return Sparse(indices=e.indices.tolist(), values=e.values.tolist())

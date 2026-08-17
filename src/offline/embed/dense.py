"""Dense embedding model, dùng chung cho index và query.

Index và query phải đi qua cùng file này: lệch model, lệch normalize hay lệch
prefix không ném lỗi, chỉ làm điểm số truy hồi kém.
"""

from __future__ import annotations

from functools import lru_cache

from langchain_core.embeddings import Embeddings

from ...branch_sql.config import (
    EMBED_BATCH,
    EMBED_MODEL,
    NORMALIZE_EMBEDDINGS,
    PASSAGE_PREFIX,
    QUERY_PREFIX,
)


@lru_cache(maxsize=1)
def get_embeddings() -> Embeddings:
    """Nạp model một lần cho cả tiến trình."""
    from langchain_huggingface import HuggingFaceEmbeddings

    return HuggingFaceEmbeddings(
        model_name=EMBED_MODEL,
        encode_kwargs={
            "normalize_embeddings": NORMALIZE_EMBEDDINGS,
            "batch_size": EMBED_BATCH,
        },
    )


def embed_passages(texts: list[str]) -> list[list[float]]:
    """Mã hoá document để index."""
    prefixed = [PASSAGE_PREFIX + t for t in texts] if PASSAGE_PREFIX else texts
    return get_embeddings().embed_documents(prefixed)


def embed_query(text: str) -> list[float]:
    """Mã hoá query để search."""
    return get_embeddings().embed_query(QUERY_PREFIX + text if QUERY_PREFIX else text)

"""Dense embedding model + tokenizer. Dùng chung cho index và query.

Index và query PHẢI đi qua cùng file này: lệch model, lệch normalize hay lệch
prefix không ném lỗi, chỉ làm điểm truy hồi kém một cách âm thầm.

Nạp qua `HuggingFaceEmbeddings` của LangChain để nối thẳng được vào chain, nhưng
vẫn giữ tay nắm tới `SentenceTransformer` bên dưới (`.client`) - đó là chỗ duy
nhất lấy được tokenizer thật và `max_seq_length` thật của model. Đếm token bằng
tokenizer khác, hay ước lượng theo ký tự, là cách chắc chắn nhất để chunk bị cắt
cụt mà không ai biết.
"""

from __future__ import annotations

from functools import lru_cache

import numpy as np
from langchain_core.embeddings import Embeddings

from ...config import (
    EMBED_BATCH,
    EMBED_DIM,
    EMBED_MAX_TOKENS,
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


def _st():
    """SentenceTransformer nằm dưới wrapper của LangChain.

    Tên thuộc tính đổi giữa các bản `langchain-huggingface` (`client` -> `_client`),
    nên dò cả hai thay vì ghim một cái rồi vỡ khi nâng version.
    """
    emb = get_embeddings()
    for attr in ("client", "_client"):
        if (st := getattr(emb, attr, None)) is not None:
            return st
    raise AttributeError(
        "không lấy được SentenceTransformer từ HuggingFaceEmbeddings - "
        "bản langchain-huggingface này đổi tên thuộc tính, sửa `_st()`"
    )


@lru_cache(maxsize=1)
def context_limit() -> int:
    """Số token tối đa model THẬT SỰ đọc được.

    Lấy giá trị nhỏ hơn giữa `max_seq_length` của model và `embed.dense.max_tokens`
    của profile. Profile khai to hơn model là khai sai - im lặng tin nó thì phần
    đuôi chunk bị cắt trước khi vào vector.
    """
    return min(int(_st().max_seq_length), EMBED_MAX_TOKENS)


def count_tokens(texts: list[str]) -> list[int]:
    """Số token của từng text, đếm bằng đúng tokenizer của model.

    `add_special_tokens=True` vì [CLS]/[SEP] cũng chiếm chỗ trong context - bỏ
    chúng ra là đếm thiếu đúng hai token ở ngưỡng quan trọng nhất.
    """
    tok = _st().tokenizer
    return [len(ids) for ids in tok(texts, add_special_tokens=True)["input_ids"]]


def embed_passages(texts: list[str]) -> np.ndarray:
    """Mã hoá document để index. Trả ma trận `(n, dim)` float32.

    SentenceTransformer tự gom batch theo độ dài nên không cần tự chia lô; chỉ
    cần truyền `batch_size` từ profile.
    """
    prefixed = [PASSAGE_PREFIX + t for t in texts] if PASSAGE_PREFIX else texts
    vectors = _st().encode(
        prefixed,
        batch_size=EMBED_BATCH,
        normalize_embeddings=NORMALIZE_EMBEDDINGS,
        convert_to_numpy=True,
        show_progress_bar=False,
    )
    return np.asarray(vectors, dtype=np.float32)


def embed_query(text: str) -> list[float]:
    """Mã hoá query để search."""
    return get_embeddings().embed_query(QUERY_PREFIX + text if QUERY_PREFIX else text)


def check_dim(vectors: np.ndarray) -> None:
    """Chiều của model phải khớp `embed.dense.dim` trong profile.

    Lệch chiều thì Qdrant từ chối lúc upsert với thông báo khó lần ra nguyên
    nhân; bắt ở đây thì thông báo nói thẳng phải sửa gì.
    """
    if vectors.ndim != 2 or vectors.shape[1] != EMBED_DIM:
        got = vectors.shape[1] if vectors.ndim == 2 else vectors.shape
        raise ValueError(
            f"model '{EMBED_MODEL}' cho vector {got} chiều nhưng profile khai "
            f"embed.dense.dim={EMBED_DIM}. Sửa profile rồi index lại toàn bộ."
        )

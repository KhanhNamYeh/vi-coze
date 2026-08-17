"""Luồng online: query -> hybrid (RRF) -> rerank -> top N chunk.

    docker compose up -d
    uv run python -m src.branch_sql.online
    uv run python -m src.branch_sql.online "câu hỏi khác"

Chỉ truy hồi, không gọi LLM.
"""

from __future__ import annotations

import sys

from langchain_classic.retrievers import ContextualCompressionRetriever, EnsembleRetriever
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever

from ..config import (
    CANDIDATE_K,
    COLLECTION,
    RERANK_MODEL,
    RERANK_TOP_N,
    RRF_K,
    RRF_WEIGHTS,
)
from .rerank import ScoringReranker, get_reranker
from .qdrant_retriever import QdrantRetriever

# Query tạm thời, chưa nối vào API.
QUERY = "Bảng nào lưu doanh thu tài khoản chính theo phường xã?"


def build_retriever(
    *,
    candidate_k: int = CANDIDATE_K,
    rrf_k: int = RRF_K,
    top_n: int = RERANK_TOP_N,
) -> BaseRetriever:
    """dense + sparse -> RRF -> cross-encoder rerank."""
    fused = EnsembleRetriever(
        retrievers=[
            QdrantRetriever(mode="dense", k=candidate_k),
            QdrantRetriever(mode="sparse", k=candidate_k),
        ],
        weights=RRF_WEIGHTS,
        c=rrf_k,
    )
    return ContextualCompressionRetriever(
        base_compressor=ScoringReranker(model=get_reranker(), top_n=top_n),
        base_retriever=fused,
    )


def run(query: str) -> list[Document]:
    return build_retriever().invoke(query)


def main(argv: list[str]) -> int:
    query = argv[0] if argv else QUERY

    print(f'query      : "{query}"')
    print(f"collection : {COLLECTION}")
    print(f"hybrid     : dense + bm25, RRF k={RRF_K}, weights={RRF_WEIGHTS}, {CANDIDATE_K} ứng viên/nhánh")
    print(f"rerank     : {RERANK_MODEL} -> top {RERANK_TOP_N}\n")

    try:
        docs = run(query)
    except Exception as e:  # noqa: BLE001
        print(f"lỗi: {e}", file=sys.stderr)
        print("Qdrant đã chạy chưa?  docker compose up -d", file=sys.stderr)
        return 1

    if not docs:
        print("không có kết quả - collection rỗng? chạy src.branch_sql.offline trước")
        return 1

    for i, d in enumerate(docs, 1):
        m = d.metadata
        print(f"[{i}] {m.get('rerank_score', float('nan')):+.4f}  {m.get('no'):<5} {m.get('table_name')}")
        print(f"    {m.get('section')}")
        print(f"    {' '.join(d.page_content.split())[:130]}...\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

"""Hybrid search: dense + BM25, Qdrant fuse bằng RRF.

    uv run python -m src.retrieval.retriever "bảng nào lưu doanh thu TKC"

Chỉ search, không gọi LLM.
"""

from __future__ import annotations

import sys

from langchain_core.callbacks import CallbackManagerForRetrieverRun
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever

from ..config_sql import CANDIDATE_K, COLLECTION, DENSE_VECTOR, SPARSE_VECTOR
from .embeddings import embed_query
from .sparse import encode_query


def search(
    query: str,
    *,
    k: int = 5,
    prefetch: int = 20,
    mode: str = "hybrid",
    section: str | None = None,
) -> list[tuple[float, Document]]:
    """Trả [(score, Document)] đã sắp giảm dần.

    mode "dense" và "sparse" dùng để so sánh khi tune; production dùng "hybrid".
    """
    from qdrant_client import models

    from .store import get_client

    client = get_client()

    flt = (
        models.Filter(must=[models.FieldCondition(key="section", match=models.MatchValue(value=section))])
        if section
        else None
    )

    if mode == "dense":
        res = client.query_points(
            COLLECTION, query=embed_query(query), using=DENSE_VECTOR,
            limit=k, query_filter=flt, with_payload=True,
        )
    elif mode == "sparse":
        sv = encode_query(query)
        res = client.query_points(
            COLLECTION,
            query=models.SparseVector(indices=sv.indices, values=sv.values),
            using=SPARSE_VECTOR, limit=k, query_filter=flt, with_payload=True,
        )
    else:
        sv = encode_query(query)
        res = client.query_points(
            COLLECTION,
            # lấy dư `prefetch` ở mỗi nhánh rồi để RRF chọn lại `k`
            prefetch=[
                models.Prefetch(query=embed_query(query), using=DENSE_VECTOR, limit=prefetch, filter=flt),
                models.Prefetch(
                    query=models.SparseVector(indices=sv.indices, values=sv.values),
                    using=SPARSE_VECTOR, limit=prefetch, filter=flt,
                ),
            ],
            query=models.FusionQuery(fusion=models.Fusion.RRF),
            limit=k, with_payload=True,
        )

    out = []
    for p in res.points:
        payload = dict(p.payload or {})
        text = payload.pop("text", "")
        out.append((p.score, Document(page_content=text, metadata=payload)))
    return out


class QdrantRetriever(BaseRetriever):
    """Bọc `search` thành BaseRetriever để nối vào chain của LangChain."""

    mode: str = "hybrid"
    k: int = CANDIDATE_K
    section: str | None = None

    def _get_relevant_documents(
        self, query: str, *, run_manager: CallbackManagerForRetrieverRun
    ) -> list[Document]:
        return [d for _, d in search(query, k=self.k, mode=self.mode, section=self.section)]


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 1

    query = argv[0]
    print(f'truy vấn: "{query}"\n')
    for mode in ("dense", "sparse", "hybrid"):
        try:
            hits = search(query, k=3, mode=mode)
        except Exception as e:  # noqa: BLE001
            print(f"lỗi ({mode}): {e}", file=sys.stderr)
            return 1
        print(f"--- {mode} ---")
        for score, d in hits:
            print(f"  {score:.4f}  {d.metadata.get('no'):<5} {d.metadata.get('table_name')}")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

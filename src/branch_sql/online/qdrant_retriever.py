"""Hybrid search: dense + BM25. Đường truy hồi dùng chung cho cả đo lẫn chạy thật.

    uv run python -m src.branch_sql.online.qdrant_retriever "bảng nào lưu doanh thu"

Chỉ search, không gọi LLM.

Bốn chế độ:

    dense    chỉ vector ngữ nghĩa
    sparse   chỉ BM25
    rrf      Qdrant fuse phía server. Nhanh nhất, một vòng gọi, NHƯNG hằng số
             RRF cố định - không chỉnh được.
    wrrf     fuse phía client theo `retrieval.rrf_k` và `retrieval.rrf_weights`.
             Hai vòng gọi, đổi lại chỉnh được trọng số giữa hai nhánh.

Có `wrrf` vì profile đã khai `rrf_k` và `rrf_weights`: một khoá mà code không đọc
còn tệ hơn không có khoá. Muốn nhanh thì tune bằng `wrrf` rồi chốt sang `rrf`
nếu trọng số tối ưu hoá ra là 50/50.
"""

from __future__ import annotations

import sys
from collections import defaultdict

from langchain_core.callbacks import CallbackManagerForRetrieverRun
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever

from ..config import (
    CANDIDATE_K,
    COLLECTION,
    DENSE_VECTOR,
    RRF_K,
    RRF_WEIGHTS,
    SPARSE_VECTOR,
)
from ..offline.embed.dense import embed_query
from ..offline.embed.sparse import encode_query


def _filter(doc_id: str | None = None, section: str | None = None):
    from qdrant_client import models

    must = [
        models.FieldCondition(key=key, match=models.MatchValue(value=value))
        for key, value in (("doc_id", doc_id), ("section", section))
        if value
    ]
    return models.Filter(must=must) if must else None


def _to_doc(point) -> tuple[float, Document]:
    payload = dict(point.payload or {})
    return point.score, Document(page_content=payload.pop("text", ""), metadata=payload)


def search(
    query: str,
    *,
    k: int = 5,
    candidate_k: int = CANDIDATE_K,
    mode: str = "rrf",
    rrf_k: int = RRF_K,
    weights: tuple[float, float] = tuple(RRF_WEIGHTS),
    doc_id: str | None = None,
    section: str | None = None,
    collection: str = COLLECTION,
) -> list[tuple[float, Document]]:
    """Trả `[(score, Document)]` đã sắp giảm dần.

    `candidate_k` là số ứng viên lấy ở MỖI nhánh trước khi fuse; nó phải lớn hơn
    `k` thì fusion mới có gì để xếp lại.
    """
    from qdrant_client import models

    from ..offline.index.qdrant_store import get_client

    client = get_client()
    flt = _filter(doc_id, section)

    def dense_query(limit: int):
        return client.query_points(
            collection, query=embed_query(query), using=DENSE_VECTOR,
            limit=limit, query_filter=flt, with_payload=True,
        ).points

    def sparse_query(limit: int):
        sv = encode_query(query)
        return client.query_points(
            collection,
            query=models.SparseVector(indices=sv.indices, values=sv.values),
            using=SPARSE_VECTOR, limit=limit, query_filter=flt, with_payload=True,
        ).points

    if mode == "dense":
        return [_to_doc(p) for p in dense_query(k)]
    if mode == "sparse":
        return [_to_doc(p) for p in sparse_query(k)]

    if mode == "rrf":
        sv = encode_query(query)
        res = client.query_points(
            collection,
            # lấy dư `candidate_k` ở mỗi nhánh rồi để RRF chọn lại `k`
            prefetch=[
                models.Prefetch(query=embed_query(query), using=DENSE_VECTOR,
                                limit=candidate_k, filter=flt),
                models.Prefetch(query=models.SparseVector(indices=sv.indices, values=sv.values),
                                using=SPARSE_VECTOR, limit=candidate_k, filter=flt),
            ],
            query=models.FusionQuery(fusion=models.Fusion.RRF),
            limit=k, with_payload=True,
        )
        return [_to_doc(p) for p in res.points]

    if mode != "wrrf":
        raise ValueError(f"mode '{mode}' không hợp lệ - dense | sparse | rrf | wrrf")

    # Weighted RRF phía client: score = Σ wᵢ / (rrf_k + rankᵢ)
    ranked = [dense_query(candidate_k), sparse_query(candidate_k)]
    scores: dict[str, float] = defaultdict(float)
    seen: dict[str, object] = {}
    for weight, points in zip(weights, ranked):
        for rank, p in enumerate(points):
            scores[str(p.id)] += weight / (rrf_k + rank + 1)
            seen.setdefault(str(p.id), p)

    top = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)[:k]
    return [(score, _to_doc(seen[pid])[1]) for pid, score in top]


class QdrantRetriever(BaseRetriever):
    """Bọc `search` thành BaseRetriever để nối vào chain của LangChain."""

    mode: str = "rrf"
    k: int = 5
    candidate_k: int = CANDIDATE_K
    doc_id: str | None = None
    section: str | None = None

    def _get_relevant_documents(
        self, query: str, *, run_manager: CallbackManagerForRetrieverRun
    ) -> list[Document]:
        return [
            d for _, d in search(
                query, k=self.k, candidate_k=self.candidate_k, mode=self.mode,
                doc_id=self.doc_id, section=self.section,
            )
        ]


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 1

    query = argv[0]
    print(f'truy vấn: "{query}"\n')
    for mode in ("dense", "sparse", "rrf", "wrrf"):
        try:
            hits = search(query, k=3, mode=mode)
        except Exception as e:  # noqa: BLE001
            print(f"lỗi ({mode}): {e}", file=sys.stderr)
            return 1
        print(f"--- {mode} ---")
        for score, d in hits:
            print(f"  {score:.4f}  {d.metadata.get('doc_id', '')[-4:]:<5} "
                  f"{d.metadata.get('table_name')}")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

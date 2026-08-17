"""Luồng online của nhánh PDF: query -> similarity search -> rerank -> top N chunk.

    uv sync --extra rag_docs
    uv run python -m src.branch_rag_docs.online "câu hỏi"

Chỉ truy hồi, không gọi LLM.

Đối xứng với `src/branch_sql/online.py`, nhưng yếu hơn ở hai chỗ và nên biết rõ
khi so sánh kết quả hai nhánh:

    - chỉ có dense, không có nhánh BM25 nên không hybrid, không RRF
    - Chroma trả về khoảng cách, không phải điểm tương đồng, nên số nhỏ là tốt
"""

from __future__ import annotations

import sys

from .. import config

QUERY = "RAG là gì và gồm những thành phần nào?"


def run(query: str, *, candidate_k: int = config.CANDIDATE_K,
        top_n: int = config.RERANK_TOP_N) -> list[dict]:
    """Trả [{"document", "vector_distance", "reranker_score"}] đã sắp giảm dần."""
    from .bge_reranker import LegalReranker
    from .chroma_retriever import load_vector_db

    db = load_vector_db(config.CHROMA_DIR, config.EMBED_MODEL)
    hits = db.similarity_search_with_score(query, k=candidate_k)
    candidates = [{"document": d, "vector_distance": float(s)} for d, s in hits]

    if not candidates:
        return []

    reranker = LegalReranker(model_name=config.RERANK_MODEL)
    return reranker.rerank(query, candidates, top_k=top_n)


def main(argv: list[str]) -> int:
    query = argv[0] if argv else QUERY

    print(f'query      : "{query}"')
    print(f"store      : {config.rel(config.CHROMA_DIR)} | collection '{config.COLLECTION}'")
    print(f"embedding  : {config.EMBED_MODEL}, {config.CANDIDATE_K} ứng viên (chỉ dense)")
    print(f"rerank     : {config.RERANK_MODEL} -> top {config.RERANK_TOP_N}\n")

    try:
        results = run(query)
    except ImportError as e:
        print(f"thiếu thư viện: {e}", file=sys.stderr)
        print("chạy:  uv sync --extra rag_docs", file=sys.stderr)
        return 1
    except Exception as e:  # noqa: BLE001
        print(f"lỗi: {e}", file=sys.stderr)
        print(f"đã index chưa?  python -m src.branch_rag_docs.offline <file.pdf>", file=sys.stderr)
        return 1

    if not results:
        print("không có kết quả - store rỗng? chạy branch_rag_docs.offline trước")
        return 1

    for i, r in enumerate(results, 1):
        doc = r["document"]
        page = doc.metadata.get("page", "?")
        print(f"[{i}] rerank={r['reranker_score']:.4f}  dist={r['vector_distance']:.4f}  trang {page}")
        print(f"    {' '.join(doc.page_content.split())[:130]}...\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

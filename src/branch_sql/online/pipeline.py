"""Luồng online: query -> hai vế truy hồi -> rerank -> ngữ cảnh cho LLM.

    docker compose up -d
    VI_COZE_PROJECT=1 uv run python -m src.branch_sql.online "câu hỏi"
    VI_COZE_PROJECT=1 uv run python -m src.branch_sql.online "câu hỏi" --wide 20

Chỉ truy hồi, không gọi LLM.

HAI VẾ, hai trần khác nhau - đúng cách `verify/score.py` chấm điểm:

    tài liệu     top-5   `..__docs`   mô tả bảng, cột, quan hệ
    SQL sample   top-3   `..__sql`    mẫu câu hỏi + SQL đã viết sẵn

Trước đây file này chỉ hỏi vế tài liệu, nên điểm báo cáo `(docs@5 + sql@3)/2`
KHÔNG phải thứ online cho ra - hai đường mô tả cùng một việc rồi rời nhau. Giờ
cả hai đi qua chung hàm `search()` với `verify/score.py`, nên đo được gì là chạy
đúng cái đó.

Vế SQL sample trả về `parent_text`: con chỉ chứa câu hỏi (28-52 token) để vector
thuần và khớp chính xác, còn thứ đưa cho LLM là cả mẫu gồm query, evidence và
câu SQL. Một vòng gọi, không phải tra thêm docstore.

RERANK chỉ SẮP XẾP LẠI, không đổi tập kết quả, nên recall giữ nguyên bằng số đã
đo. Muốn reranker thật sự lọc thì dùng `--wide N`: lấy N ứng viên rồi cắt xuống
trần - có thể tốt hơn, nhưng CHƯA ĐƯỢC ĐO, đừng báo cáo số của nó.
"""

from __future__ import annotations

import sys

from langchain_core.documents import Document

from ..config import CANDIDATE_K, RERANK_MODEL, RERANK_TOP_N, collections_of
from .qdrant_retriever import search
from .rerank import get_reranker

K_DOCS = 5
K_SQL = 3

QUERY = "Bảng nào lưu doanh thu tài khoản chính theo phường xã?"


def _rerank(query: str, docs: list[Document], top_n: int) -> list[Document]:
    """Cross-encoder chấm lại rồi sắp giảm dần. Giữ nguyên `top_n` phần tử."""
    if not docs:
        return docs
    model = get_reranker()
    scores = model.score([(query, d.page_content) for d in docs])
    ranked = sorted(zip(scores, docs), key=lambda x: x[0], reverse=True)
    out = []
    for score, doc in ranked[:top_n]:
        doc.metadata["rerank_score"] = float(score)
        out.append(doc)
    return out


def retrieve(
    query: str,
    *,
    project: int | None = None,
    k_docs: int = K_DOCS,
    k_sql: int = K_SQL,
    wide: int | None = None,
    rerank: bool = True,
    mode: str = "rrf",
) -> dict[str, list[Document]]:
    """-> `{"docs": [...], "sql": [...]}`.

    `wide` lấy dư ứng viên rồi để reranker cắt xuống trần. Bỏ trống thì lấy đúng
    trần và reranker chỉ sắp lại - đó là cấu hình khớp với số đã đo.
    """
    docs_coll, sql_coll = collections_of(project)
    out: dict[str, list[Document]] = {}

    for leg, coll, k in (("docs", docs_coll, k_docs), ("sql", sql_coll, k_sql)):
        if not coll:
            out[leg] = []
            continue
        hits = search(query, k=wide or k, mode=mode,
                      candidate_k=CANDIDATE_K, collection=coll)
        found = [doc for _, doc in hits]
        out[leg] = _rerank(query, found, k) if rerank else found[:k]

    # Vế sample: thứ đưa cho LLM là CẢ MẪU, không phải câu hỏi đã khớp.
    for doc in out["sql"]:
        if parent := doc.metadata.get("parent_text"):
            doc.page_content = parent
    return out


def run(query: str, **kw) -> list[Document]:
    """Ngữ cảnh phẳng để nhét vào prompt: tài liệu trước, mẫu SQL sau."""
    res = retrieve(query, **kw)
    return [*res["docs"], *res["sql"]]


def main(argv: list[str]) -> int:
    args = [a for a in argv if not a.startswith("--")]
    wide = None
    if "--wide" in argv:
        i = argv.index("--wide")
        wide = int(argv[i + 1]) if i + 1 < len(argv) else 20
        args = [a for a in args if a != str(wide)]
    no_rerank = "--no-rerank" in argv
    query = args[0] if args else QUERY

    try:
        docs_coll, sql_coll = collections_of()
    except ValueError as e:
        print(e, file=sys.stderr)
        print("đặt VI_COZE_PROJECT=<id> rồi chạy lại", file=sys.stderr)
        return 1

    print(f'query      : "{query}"')
    print(f"tài liệu   : {docs_coll} · top-{K_DOCS}")
    print(f"SQL sample : {sql_coll or '(dự án không khai)'} · top-{K_SQL} · trả parent_text")
    print(f"hybrid     : dense + bm25, RRF phía Qdrant, {CANDIDATE_K} ứng viên/nhánh")
    if no_rerank:
        print("rerank     : tắt")
    elif wide:
        print(f"rerank     : {RERANK_MODEL} · lấy {wide} rồi cắt xuống trần (CHƯA ĐO)")
    else:
        print(f"rerank     : {RERANK_MODEL} · chỉ sắp lại, không đổi tập kết quả")
    print()

    try:
        res = retrieve(query, wide=wide, rerank=not no_rerank)
    except Exception as e:  # noqa: BLE001
        print(f"lỗi: {e}", file=sys.stderr)
        print("Qdrant đã chạy chưa?  docker compose up -d", file=sys.stderr)
        return 1

    if not any(res.values()):
        print("không có kết quả - collection rỗng? chạy src.branch_sql.offline trước")
        return 1

    for leg, title in (("docs", "TÀI LIỆU"), ("sql", "SQL SAMPLE")):
        if not res[leg]:
            continue
        print(f"--- {title} ({len(res[leg])}) ---")
        for i, d in enumerate(res[leg], 1):
            m = d.metadata
            score = m.get("rerank_score")
            head = f"{score:+.4f}" if score is not None else "      "
            print(f"[{i}] {head}  {m.get('no', ''):<5} {m.get('table_name')}")
            print(f"    {' '.join(d.page_content.split())[:120]}...")
        print()

    tables = sorted({d.metadata.get("table_name") for d in res["docs"] if d.metadata.get("table_name")})
    print(f"bảng đưa vào prompt: {', '.join(tables) or '(không có)'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

"""Nạp profile của nhánh SQL.

Tham số thật nằm ở `config/sql.json`, không nằm ở đây. File này chỉ đọc profile
lên thành object và trải ra thành hằng số cho các chặng dùng:

    from .config import CFG          # object, có kiểu, đọc được cả cây
    from .config import BUDGET_MAX   # lối tắt cho một giá trị lẻ

Chạy profile khác mà không sửa code:

    VI_COZE_PROFILE=sql_v2 uv run python -m src.branch_sql.offline "file.docx"

`data/` chia theo vai trò trước, rồi mới theo bộ tài liệu:

    data/raw/<kb>/        đầu vào, người dùng cung cấp — pipeline không ghi vào đây
    data/processed/<kb>/  artifact sinh ra, xoá đi chạy lại được
    data/index/           vector store nằm trên đĩa
    data/eval/<kb>/       bộ gold để đo độ chính xác
"""

from __future__ import annotations

import os
from pathlib import Path

from ..config import KBConfig, listdir, rel, require, resolve  # noqa: F401  (re-export)

PROFILE = os.getenv("VI_COZE_PROFILE", "sql")
CFG = KBConfig.load(PROFILE)

# ---- đường dẫn ------------------------------------------------------------
ROOT = CFG.root
DATA_DIR = ROOT / "data"
KB = CFG.kb

RAW_DIR = CFG.raw_dir
PROCESSED_DIR = CFG.processed_dir
EVAL_DIR = CFG.eval_dir
INDEX_DIR = CFG.index_dir

KNOWLEDGE_DIR = CFG.knowledge_dir
KG_INDEX = INDEX_DIR / "kb_index.npz"

DOC_SUFFIXES = set(CFG.parse.suffixes)

# ---- cấu trúc heading -----------------------------------------------------
# Extract là chặng đọc heading, nên mapping này thuộc `extract.heading_roles`.
# Các module cũ phía sau nếu được gọi riêng chỉ tiêu thụ kết quả đó, không còn
# là nguồn cấu hình ngược cho extract.
HEADING_ROLES = CFG.extract.heading_roles

# ---- chunk ----------------------------------------------------------------
CHUNK = CFG.chunk
BUDGET_MAX = CFG.chunk.budget.max
BUDGET_MIN = CFG.chunk.budget.min

# ---- embedding ------------------------------------------------------------
# Đổi model thì phải đổi `index.collection` trong profile và index lại toàn bộ.
EMBED_MODEL = CFG.embed.dense.model
EMBED_DIM = CFG.embed.dense.dim
EMBED_MAX_TOKENS = CFG.embed.dense.max_tokens
EMBED_BATCH = CFG.embed.dense.batch
NORMALIZE_EMBEDDINGS = CFG.embed.dense.normalize
QUERY_PREFIX = CFG.embed.dense.query_prefix
PASSAGE_PREFIX = CFG.embed.dense.passage_prefix

# ---- sparse / BM25 --------------------------------------------------------
_sparse = CFG.embed.sparse
SPARSE_MODEL = _sparse.model if _sparse else None
BM25_DISABLE_STEMMER = _sparse.disable_stemmer if _sparse else True
BM25_K = _sparse.k if _sparse else 1.2
BM25_B = _sparse.b if _sparse else 0.0

# ---- vector store ---------------------------------------------------------
QDRANT_URL = CFG.index.url
DENSE_VECTOR = CFG.index.dense_vector
SPARSE_VECTOR = CFG.index.sparse_vector
# `{project}` phải được thay NGAY ở đây. Để nguyên thì mọi consumer của hằng số
# này gửi lên Qdrant một tên chứa dấu ngoặc và nhận 404 rất khó lần ra nguồn.
COLLECTION = CFG.index.collection.format(project=CFG.project or "")
SQL_COLLECTION = (CFG.index.sql_collection or "").format(project=CFG.project or "") or None


def collections_of(project: int | None = None) -> tuple[str, str | None]:
    """-> `(collection tài liệu, collection SQL sample)` của một dự án.

    Nhận diện vế SQL sample bằng hậu tố `__sql` của tên collection. Trả `None`
    cho vế đó nếu dự án không khai bộ SQL sample - truy hồi vẫn chạy được với
    một vế, chỉ là mất phần mẫu.

    Đặt cạnh `collection_of` vì cả `online/` lẫn `verify/` đều cần. Khai hai bản
    là mời một bản lệch đi khi profile đổi - đã xảy ra ba lần trong repo này.
    """
    project = project if project is not None else CFG.project
    if project is None:
        return COLLECTION, SQL_COLLECTION

    docs = sql = None
    for k in CFG.knowledge_of(project):
        name = k.collection_for(project)
        if name.endswith("__sql"):
            sql = name
        else:
            docs = name
    if not docs:
        raise ValueError(
            f"dự án {project} không có bộ tri thức tài liệu nào - "
            "kiểm tra `knowledge[]` trong profile"
        )
    return docs, sql


def collection_of(doc_id: str, *, project: int | None = None) -> str:
    """Collection của bộ tri thức sinh ra `doc_id` này.

    Nguồn sự thật là `knowledge[].collection`, KHÔNG phải hằng `COLLECTION` ở
    trên - hằng đó chỉ là mặc định của profile. Từ khi mỗi bộ tri thức khai
    collection riêng, dùng hằng nghĩa là mọi tài liệu đều đổ vào collection của
    bộ ĐẦU TIÊN: chạy CLI index cho bộ SQL sample sẽ ghi nhầm nó vào collection
    tài liệu, và không có lỗi nào báo.

    Đặt ở đây chứ không ở `verify/` vì cả `index/` lẫn `verify/` đều cần, mà hai
    bên import lẫn nhau - khai hai bản là mời một bản lệch đi.
    """
    from .offline.parse.doc_parse import doc_id_of

    project = project if project is not None else CFG.project
    if project is None:
        return COLLECTION
    for k in CFG.knowledge_of(project):
        if doc_id_of(Path(k.source)) == doc_id:
            return k.collection_for(project)
    raise ValueError(
        f"không bộ tri thức nào của dự án {project} sinh ra '{doc_id}' - "
        f"kiểm tra `knowledge[].source` trong profile"
    )
PAYLOAD_INDEX_FIELDS = CFG.index.payload_index_fields

# ---- online / search ------------------------------------------------------
CANDIDATE_K = CFG.retrieval.candidate_k
RRF_K = CFG.retrieval.rrf_k
RRF_WEIGHTS = CFG.retrieval.rrf_weights
RERANK_MODEL = CFG.retrieval.rerank.model if CFG.retrieval.rerank else None
RERANK_TOP_N = CFG.retrieval.rerank.top_n if CFG.retrieval.rerank else 5

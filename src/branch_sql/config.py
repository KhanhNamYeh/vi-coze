"""Nạp profile của nhánh SQL.

Tham số thật nằm ở `config/sql.json`, không nằm ở đây. File này chỉ đọc profile
lên thành object và trải ra thành hằng số cho các chặng dùng:

    from .config import CFG          # object, có kiểu, đọc được cả cây
    from .config import MAX_CHARS    # lối tắt cho một giá trị lẻ

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

# ---- chunking -------------------------------------------------------------
HEADERS_TO_SPLIT_ON = CFG.chunk.headers_to_split_on
STRIP_HEADERS = CFG.chunk.strip_headers
CHUNK_OVERLAP = CFG.chunk.overlap
MAX_CHARS = CFG.chunk.max_chars
MIN_CHARS = CFG.chunk.min_chars

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
COLLECTION = CFG.index.collection
PAYLOAD_INDEX_FIELDS = CFG.index.payload_index_fields

# ---- online / search ------------------------------------------------------
CANDIDATE_K = CFG.retrieval.candidate_k
RRF_K = CFG.retrieval.rrf_k
RRF_WEIGHTS = CFG.retrieval.rrf_weights
RERANK_MODEL = CFG.retrieval.rerank.model if CFG.retrieval.rerank else None
RERANK_TOP_N = CFG.retrieval.rerank.top_n if CFG.retrieval.rerank else 5

"""Nạp profile của nhánh PDF.

Tham số thật nằm ở `config/rag_docs.json`. Cùng quy ước với
`branch_sql/config.py` — xem docstring ở đó.
"""

from __future__ import annotations

import os

from ..config import KBConfig, listdir, rel, require, resolve  # noqa: F401  (re-export)

PROFILE = os.getenv("VI_COZE_PROFILE_DOCS", "rag_docs")
CFG = KBConfig.load(PROFILE)

# ---- đường dẫn ------------------------------------------------------------
ROOT = CFG.root
DATA_DIR = ROOT / "data"
KB = CFG.kb

RAW_DIR = CFG.raw_dir
PROCESSED_DIR = CFG.processed_dir
EVAL_DIR = CFG.eval_dir
INDEX_DIR = CFG.index_dir

DOC_SUFFIXES = set(CFG.parse.suffixes)

# ---- artifact từng chặng --------------------------------------------------
BLOCKS = PROCESSED_DIR / "pdf_extract.jsonl"        # parse
IMAGE_META = PROCESSED_DIR / "image_metadata.jsonl"
IMAGE_CAPTIONS = PROCESSED_DIR / "image_captions.jsonl"
IMAGE_DIR = PROCESSED_DIR / "images"
MERGED = PROCESSED_DIR / "merged_documents.jsonl"   # extract
CHUNKS = PROCESSED_DIR / "chunked.jsonl"            # chunk

# ---- chunking -------------------------------------------------------------
CHUNK_SIZE = CFG.chunk.budget.max
CHUNK_OVERLAP = CFG.chunk.budget.overlap

# ---- embedding ------------------------------------------------------------
# TODO: nhánh SQL dùng AITeamVN/Vietnamese_Embedding. Còn khác model thì vector
# hai nhánh không so sánh được, không trộn kết quả được.
EMBED_MODEL = CFG.embed.dense.model

# ---- vector store ---------------------------------------------------------
# TODO: nhánh SQL dùng Qdrant. Nên gộp về một store.
CHROMA_DIR = CFG.store_dir
COLLECTION = CFG.index.collection

# ---- online ---------------------------------------------------------------
CANDIDATE_K = CFG.retrieval.candidate_k
RERANK_MODEL = CFG.retrieval.rerank.model if CFG.retrieval.rerank else None
RERANK_TOP_N = CFG.retrieval.rerank.top_n if CFG.retrieval.rerank else 5

"""Đường dẫn và tham số cho nhánh tài liệu schema SQL.

`data/` chia theo vai trò trước, rồi mới theo bộ tài liệu (KB). Trước đây hai
nhánh dùng hai cách đặt tên cho cùng một thứ (`uploads`/`artifacts` và
`raw`/`processed`), nay gộp về một:

    data/raw/<kb>/        đầu vào, người dùng cung cấp — pipeline không ghi vào đây
    data/processed/<kb>/  artifact sinh ra, xoá đi chạy lại được
    data/index/           vector store nằm trên đĩa
    data/eval/<kb>/       bộ gold để đo độ chính xác
"""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"

# Đổi bộ tài liệu khác thì sửa đúng dòng này.
KB = "sql"

RAW_DIR = DATA_DIR / "raw" / KB
PROCESSED_DIR = DATA_DIR / "processed" / KB
EVAL_DIR = DATA_DIR / "eval" / KB
INDEX_DIR = DATA_DIR / "index"

# Knowledge graph: artifact trung gian giữa markdown và chunk.
KNOWLEDGE_DIR = PROCESSED_DIR / "knowledge"
KG_INDEX = INDEX_DIR / "kb_index.npz"

DOC_SUFFIXES = {".docx", ".doc", ".pdf", ".pptx", ".xlsx", ".html", ".htm"}

# ---- chunking ------------------------------------------------------------
HEADERS_TO_SPLIT_ON = [("#", "section"), ("##", "table")]
STRIP_HEADERS = False
CHUNK_OVERLAP = 0
MAX_CHARS = 6000
MIN_CHARS = 200

# ---- embedding -----------------------------------------------------------
# Đổi model thì phải đổi COLLECTION và index lại toàn bộ.
EMBED_MODEL = "AITeamVN/Vietnamese_Embedding"
EMBED_DIM = 1024
EMBED_MAX_TOKENS = 2048
EMBED_BATCH = 16
NORMALIZE_EMBEDDINGS = True

# Rỗng với họ bge-m3. Họ E5 bắt buộc "query: " / "passage: ".
QUERY_PREFIX = ""
PASSAGE_PREFIX = ""

# ---- sparse / BM25 -------------------------------------------------------
SPARSE_MODEL = "Qdrant/bm25"

# Snowball không có tiếng Việt; stemmer tiếng Anh cắt sai cả từ thường lẫn
# định danh SQL. FastEmbed đồng thời không dùng stopwords khi tắt stemmer.
BM25_DISABLE_STEMMER = True

# b=0 tắt chuẩn hoá theo độ dài. Corpus SaaS có nhiều loại tài liệu và thay đổi
# liên tục, nên không phụ thuộc vào một avg_len phải đo rồi re-index khi nó lệch.
BM25_K = 1.2
BM25_B = 0.0

# ---- vector store --------------------------------------------------------
QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")

DENSE_VECTOR = "dense"
SPARSE_VECTOR = "bm25"

# Tên mang theo model, số chiều và version chunking để vector khác thế hệ
# không lẫn vào nhau.
CHUNKING_VERSION = "c1"
COLLECTION = f"sqldocs__vnemb_{EMBED_DIM}__{CHUNKING_VERSION}"

PAYLOAD_INDEX_FIELDS = ["doc_id", "table_name", "section"]

# ---- online / search -----------------------------------------------------
# Số ứng viên lấy ở MỖI nhánh trước khi fuse.
CANDIDATE_K = 20

# Hằng số RRF: score = sum(1 / (RRF_K + rank)). Qdrant không cho chỉnh hằng số
# này nên phần fuse chạy ở client qua EnsembleRetriever.
RRF_K = 40
RRF_WEIGHTS = [0.5, 0.5]  # [dense, sparse]

RERANK_MODEL = "AITeamVN/Vietnamese_Reranker"
RERANK_TOP_N = 5


def resolve(name: str | Path, base: Path) -> Path:
    """Tên file -> đường dẫn đầy đủ.

    Đường dẫn tuyệt đối giữ nguyên; có `/` thì tính từ gốc repo; chỉ có tên
    file thì tìm trong `base`.
    """
    p = Path(name)
    if p.is_absolute():
        return p
    if len(p.parts) > 1:
        return (ROOT / p).resolve()
    return (base / p).resolve()


def listdir(base: Path, pattern: str = "*") -> list[str]:
    """Tên các file trong thư mục, bỏ file ẩn."""
    if not base.is_dir():
        return []
    return sorted(p.name for p in base.glob(pattern) if p.is_file() and not p.name.startswith("."))


def rel(path: Path) -> str:
    """Đường dẫn tính từ gốc repo, để in ra cho gọn."""
    return path.relative_to(ROOT).as_posix() if path.is_relative_to(ROOT) else str(path)


def require(path: Path, base: Path) -> Path:
    """Trả về path, hoặc báo lỗi kèm danh sách file có sẵn."""
    if path.exists():
        return path
    listing = "\n".join(f"  - {n}" for n in listdir(base)) or "  (thư mục rỗng)"
    raise FileNotFoundError(f"không thấy {rel(path)}\n\ncó sẵn trong {rel(base)}:\n{listing}")

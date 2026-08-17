"""Đường dẫn và tham số cho nhánh tài liệu PDF.

Cùng quy ước `data/` với `branch_sql/config.py`: chia theo vai trò trước, rồi
mới theo bộ tài liệu.

    data/raw/rag_docs/        .pdf người dùng cung cấp
    data/processed/rag_docs/  block, chunk, caption sinh ra
    data/index/chroma/        vector store
    data/eval/rag_docs/       bộ gold
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"

KB = "rag_docs"

RAW_DIR = DATA_DIR / "raw" / KB
PROCESSED_DIR = DATA_DIR / "processed" / KB
EVAL_DIR = DATA_DIR / "eval" / KB
INDEX_DIR = DATA_DIR / "index"

# ---- artifact từng chặng --------------------------------------------------
BLOCKS = PROCESSED_DIR / "pdf_extract.jsonl"       # parse
IMAGE_META = PROCESSED_DIR / "image_metadata.jsonl"
IMAGE_CAPTIONS = PROCESSED_DIR / "image_captions.jsonl"
IMAGE_DIR = PROCESSED_DIR / "images"
MERGED = PROCESSED_DIR / "merged_documents.jsonl"  # extract
CHUNKS = PROCESSED_DIR / "chunked.jsonl"           # chunk

DOC_SUFFIXES = {".pdf"}

# ---- chunking -------------------------------------------------------------
# Khác nhánh SQL: tài liệu văn bản không có ranh giới cấu trúc rõ như bảng, nên
# cắt theo độ dài và phải có overlap để câu bị cắt giữa chừng vẫn còn ngữ cảnh.
CHUNK_SIZE = 1000
CHUNK_OVERLAP = 150

# ---- embedding ------------------------------------------------------------
# TODO: nhánh SQL dùng AITeamVN/Vietnamese_Embedding 1024 chiều. Còn khác model
# thì vector hai nhánh không so sánh được, không trộn kết quả được.
EMBED_MODEL = "BAAI/bge-m3"

# ---- vector store ---------------------------------------------------------
# TODO: nhánh SQL dùng Qdrant. Nên gộp về một store.
CHROMA_DIR = INDEX_DIR / "chroma"
COLLECTION = "rag_documents"

# ---- online ---------------------------------------------------------------
CANDIDATE_K = 20
RERANK_MODEL = "BAAI/bge-reranker-v2-m3"
RERANK_TOP_N = 5


def rel(path: Path) -> str:
    """Đường dẫn tính từ gốc repo, để in ra cho gọn."""
    return path.relative_to(ROOT).as_posix() if path.is_relative_to(ROOT) else str(path)


def listdir(base: Path, pattern: str = "*") -> list[str]:
    """Tên các file trong thư mục, bỏ file ẩn."""
    if not base.is_dir():
        return []
    return sorted(p.name for p in base.glob(pattern) if p.is_file() and not p.name.startswith("."))


def resolve(name: str | Path, base: Path) -> Path:
    """Tên file -> đường dẫn đầy đủ. Có `/` thì tính từ gốc repo."""
    p = Path(name)
    if p.is_absolute():
        return p
    if len(p.parts) > 1:
        return (ROOT / p).resolve()
    return (base / p).resolve()


def require(path: Path, base: Path) -> Path:
    """Trả về path, hoặc báo lỗi kèm danh sách file có sẵn."""
    if path.exists():
        return path
    listing = "\n".join(f"  - {n}" for n in listdir(base)) or "  (thư mục rỗng)"
    raise FileNotFoundError(f"không thấy {rel(path)}\n\ncó sẵn trong {rel(base)}:\n{listing}")

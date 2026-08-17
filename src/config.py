"""Hợp đồng config: JSON là nguồn sự thật, class ở đây chỉ để đọc và kiểm.

Mỗi bộ tài liệu là một **profile** — một file JSON trong `config/`. Profile mô tả
tài liệu này được xử lý bằng cách nào: dùng loader nào, cắt chunk kiểu gì, embed
bằng model nào, đẩy vào store nào, truy hồi ra sao.

    config/sql.json         nhánh tài liệu mô tả schema CSDL
    config/rag_docs.json    nhánh tài liệu PDF

Đọc lên bằng:

    from src.config import KBConfig
    cfg = KBConfig.load("sql")
    cfg.chunk.max_chars          # 6000
    cfg.processed_dir            # <repo>/data/processed/sql

Các khoá trong JSON đặt trùng tên với thư mục chặng trong `<nhánh>/offline/`,
nên nhìn profile là biết chặng nào chạy với tham số gì:

    parse  extract  link  chunk  embed  index  retrieval

Thêm profile mới thì thêm một file JSON, không phải sửa code. Đó là điều kiện để
sau này người dùng tự chọn cách xử lý tài liệu của họ.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, model_validator

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
PROFILE_DIR = ROOT / "config"


# ---- chặng parse ----------------------------------------------------------
class CleanCfg(BaseModel):
    """Làm sạch sau khi chuyển sang text. Tắt cái nào thì bỏ cảnh báo cái đó."""

    normalize_nfc: bool = True
    strip_invisible: bool = True
    strip_html: bool = True
    block_injection: bool = True

    model_config = {"extra": "forbid"}


class ParseCfg(BaseModel):
    loader: Literal["docx_markitdown", "pdf_docling"]
    suffixes: list[str]
    clean: CleanCfg = Field(default_factory=CleanCfg)

    model_config = {"extra": "forbid"}


# ---- chặng extract / link -------------------------------------------------
class ExtractCfg(BaseModel):
    """Văn bản -> cấu trúc. `enabled: false` nghĩa là chặng này bị bỏ qua."""

    enabled: bool = False
    extractor: str | None = None  # "schema_extract" | "merge_documents"

    model_config = {"extra": "forbid"}


class LlmCfg(BaseModel):
    base_url: str = "http://localhost:11434/v1"
    model: str = "llama3"
    temperature: float = 0.1

    model_config = {"extra": "forbid"}


class LinkCfg(BaseModel):
    """Cấu trúc -> quan hệ (PK/FK, business rule, tham chiếu chéo)."""

    enabled: bool = False
    builder: str | None = None  # "knowledge_graph"
    llm: LlmCfg | None = None

    model_config = {"extra": "forbid"}


# ---- chặng chunk ----------------------------------------------------------
class ChunkCfg(BaseModel):
    """`structural` cắt theo heading, `recursive` cắt theo độ dài.

    Tài liệu có ranh giới rõ (mỗi bảng một mục) thì dùng `structural` và để
    overlap = 0. Văn bản trôi chảy thì dùng `recursive` và phải có overlap.
    """

    mode: Literal["structural", "recursive"] = "structural"

    # structural
    headers: list[list[str]] = Field(default_factory=list)  # [["#","section"], ...]
    strip_headers: bool = False

    # recursive
    chunk_size: int = 1000

    # cả hai
    overlap: int = 0
    max_chars: int = 6000  # vượt thì cảnh báo, không tự cắt
    min_chars: int = 200

    model_config = {"extra": "forbid"}

    @property
    def headers_to_split_on(self) -> list[tuple[str, str]]:
        """MarkdownHeaderTextSplitter cần tuple, JSON chỉ có list."""
        return [(h[0], h[1]) for h in self.headers]

    @model_validator(mode="after")
    def _check(self):
        if self.mode == "structural" and not self.headers:
            raise ValueError("chunk.mode = 'structural' thì phải khai báo chunk.headers")
        if self.min_chars >= self.max_chars:
            raise ValueError("chunk.min_chars phải nhỏ hơn chunk.max_chars")
        return self


# ---- chặng embed ----------------------------------------------------------
class DenseCfg(BaseModel):
    model: str
    dim: int
    batch: int = 16
    max_tokens: int = 2048
    normalize: bool = True
    # Rỗng với họ bge-m3. Họ E5 bắt buộc "query: " / "passage: ".
    query_prefix: str = ""
    passage_prefix: str = ""

    model_config = {"extra": "forbid"}


class SparseCfg(BaseModel):
    model: str = "Qdrant/bm25"
    # Snowball không có tiếng Việt; stemmer tiếng Anh cắt sai cả từ thường lẫn
    # định danh SQL. FastEmbed đồng thời không dùng stopwords khi tắt stemmer.
    disable_stemmer: bool = True
    k: float = 1.2
    # b=0 tắt chuẩn hoá theo độ dài, để không phụ thuộc một avg_len phải đo lại
    # rồi re-index mỗi khi corpus lệch.
    b: float = 0.0

    model_config = {"extra": "forbid"}


class EmbedCfg(BaseModel):
    dense: DenseCfg
    sparse: SparseCfg | None = None  # None = không có nhánh BM25, không hybrid được

    model_config = {"extra": "forbid"}


# ---- chặng index ----------------------------------------------------------
class IndexCfg(BaseModel):
    store: Literal["qdrant", "chroma"]
    collection: str
    url: str = "http://localhost:6333"  # qdrant
    subdir: str = "chroma"              # chroma, nằm dưới data/index/
    dense_vector: str = "dense"
    sparse_vector: str = "bm25"
    payload_index_fields: list[str] = Field(default_factory=list)

    model_config = {"extra": "forbid"}


# ---- luồng online ---------------------------------------------------------
class RerankCfg(BaseModel):
    model: str
    top_n: int = 5

    model_config = {"extra": "forbid"}


class RetrievalCfg(BaseModel):
    mode: Literal["hybrid", "dense", "sparse"] = "hybrid"
    candidate_k: int = 20          # số ứng viên lấy ở MỖI nhánh trước khi fuse
    rrf_k: int = 40                # score = sum(1 / (rrf_k + rank))
    rrf_weights: list[float] = Field(default_factory=lambda: [0.5, 0.5])  # [dense, sparse]
    rerank: RerankCfg | None = None

    model_config = {"extra": "forbid"}


# ---- profile --------------------------------------------------------------
class KBConfig(BaseModel):
    """Một bộ tài liệu và toàn bộ cách xử lý nó."""

    kb: str
    name: str
    description: str = ""

    parse: ParseCfg
    extract: ExtractCfg = Field(default_factory=ExtractCfg)
    link: LinkCfg = Field(default_factory=LinkCfg)
    chunk: ChunkCfg
    embed: EmbedCfg
    index: IndexCfg
    retrieval: RetrievalCfg = Field(default_factory=RetrievalCfg)

    model_config = {"extra": "forbid"}

    # ---- đường dẫn: suy từ `kb`, không lưu trong JSON để profile không dính
    # đường dẫn tuyệt đối của máy nào cả
    @property
    def root(self) -> Path:
        return ROOT

    @property
    def raw_dir(self) -> Path:
        return DATA_DIR / "raw" / self.kb

    @property
    def processed_dir(self) -> Path:
        return DATA_DIR / "processed" / self.kb

    @property
    def knowledge_dir(self) -> Path:
        return self.processed_dir / "knowledge"

    @property
    def eval_dir(self) -> Path:
        return DATA_DIR / "eval" / self.kb

    @property
    def index_dir(self) -> Path:
        return DATA_DIR / "index"

    @property
    def store_dir(self) -> Path:
        """Chỉ có nghĩa với store nằm trên đĩa (chroma)."""
        return self.index_dir / self.index.subdir

    # ---- nạp / ghi
    @classmethod
    def path_of(cls, profile: str) -> Path:
        return PROFILE_DIR / f"{profile}.json"

    @classmethod
    def load(cls, profile: str) -> "KBConfig":
        path = cls.path_of(profile)
        if not path.exists():
            avail = ", ".join(cls.available()) or "(chưa có profile nào)"
            raise FileNotFoundError(
                f"không thấy profile '{profile}' tại {path.relative_to(ROOT).as_posix()}\n"
                f"profile có sẵn: {avail}"
            )
        cfg = cls.model_validate_json(path.read_text(encoding="utf-8"))
        # Biến môi trường thắng file, để deploy không phải sửa profile.
        if cfg.index.store == "qdrant" and (url := os.getenv("QDRANT_URL")):
            cfg.index.url = url
        return cfg

    def save(self, profile: str | None = None) -> Path:
        """Ghi ngược ra JSON. Dùng khi người dùng chỉnh profile qua giao diện."""
        path = self.path_of(profile or self.kb)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(self.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return path

    @staticmethod
    def available() -> list[str]:
        if not PROFILE_DIR.is_dir():
            return []
        return sorted(p.stem for p in PROFILE_DIR.glob("*.json"))


# ---- tiện ích đường dẫn, dùng chung cho mọi nhánh -------------------------
def rel(path: Path) -> str:
    """Đường dẫn tính từ gốc repo, để in ra cho gọn."""
    return path.relative_to(ROOT).as_posix() if path.is_relative_to(ROOT) else str(path)


def listdir(base: Path, pattern: str = "*") -> list[str]:
    """Tên các file trong thư mục, bỏ file ẩn."""
    if not base.is_dir():
        return []
    return sorted(p.name for p in base.glob(pattern) if p.is_file() and not p.name.startswith("."))


def resolve(name: str | Path, base: Path) -> Path:
    """Tên file -> đường dẫn đầy đủ.

    Đường dẫn tuyệt đối giữ nguyên; có `/` thì tính từ gốc repo; chỉ có tên file
    thì tìm trong `base`.
    """
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

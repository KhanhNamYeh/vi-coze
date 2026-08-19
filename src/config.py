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
import re
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, model_validator

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
PROFILE_DIR = ROOT / "config"


# ---- chặng parse ----------------------------------------------------------
class ReplaceCfg(BaseModel):
    """Sửa lỗi gõ của tài liệu nguồn, áp lên markdown trước khi tách block.

    Ở profile chứ không ở code: "Cột2" là lỗi của MỘT file, không phải luật của
    markdown. Để nguyên thì nó thành token rác trong cả embedding lẫn BM25.
    """

    pattern: str   # regex
    replace: str

    model_config = {"extra": "forbid"}


class ParseCfg(BaseModel):
    """Chuẩn hoá NFC, bỏ ký tự vô hình / HTML / gạch ngang luôn chạy — chúng đúng
    với mọi tài liệu nên không có cờ bật tắt. Chỉ phần phụ thuộc tài liệu cụ thể
    mới nằm ở đây.

    Không có khoá `loader`: loader chọn theo ĐUÔI FILE, không theo khai báo. Một
    khoá mà code không đọc còn tệ hơn không có khoá, vì nó trông như đang điều
    khiển thứ gì đó.
    """

    suffixes: list[str]
    replacements: list[ReplaceCfg] = Field(default_factory=list)

    # Chỉ dùng cho nguồn .xlsx: vai trò -> tên sheet. `dev` được dựng thành .md
    # rồi đi tiếp vào chunk/index làm SQL sample; `test` chỉ sinh JSON để chấm.
    sheets: dict[str, str] = Field(default_factory=dict)

    # Nhận diện dòng tên bảng trong output thô của markitdown, phải có nhóm
    # `name` là phần dùng làm tiêu đề. Tài liệu này viết "* 1. **Bảng X**" vì tên
    # bảng dùng style `normal` chứ không phải Heading. Đây là quy ước của MỘT bộ
    # tài liệu nên nó phải nằm ở profile, không nằm trong code.
    table_heading: str | None = None

    model_config = {"extra": "forbid"}

    @property
    def table_heading_re(self) -> re.Pattern | None:
        return re.compile(self.table_heading) if self.table_heading else None


# ---- chặng extract / link -------------------------------------------------
class RoleCfg(BaseModel):
    """Nhãn ngữ nghĩa cho một block văn bản, nhận diện bằng biểu thức chính quy.

    Đây là chỗ DUY NHẤT biết tài liệu này viết "Mối liên kết:" hay "Relations:".
    Code chỉ biết "có nhãn thì gán role", không biết nhãn nào mang nghĩa gì.

    Tài liệu hay dùng hai kiểu nhãn, `match` xử được cả hai:

        "Ý nghĩa: Lưu trữ..."   nhãn và nội dung cùng dòng
        "Mối liên kết:"         nhãn đứng riêng, nội dung ở các dòng sau
        "Liên kết qua cột X."

    Kiểu thứ hai mà nội dung nằm ở block KHÁC thì `extract` để nhãn đứng một
    mình với `text` rỗng; ghép nó với nội dung hoặc đối tượng là việc của `link`,
    vì chỉ chặng đó dựng cây cha–con và quan hệ giữa các element.
    """

    role: str
    match: list[str]                # regex, thử theo thứ tự, khớp cái đầu tiên
    strip_label: bool = True        # bỏ phần nhãn khỏi text sau khi khớp

    model_config = {"extra": "forbid"}

    @property
    def patterns(self) -> list[re.Pattern]:
        return [re.compile(p, re.IGNORECASE) for p in self.match]


class ExtractCfg(BaseModel):
    """Block -> nội dung theo modality. `enabled: false` thì bỏ qua chặng này."""

    enabled: bool = False
    extractor: str | None = None  # "block_extract" | "merge_documents"

    # Cấp heading -> vai trò ngữ nghĩa. Đây là cấu hình của extract vì chính
    # extract đọc heading và tạo structured element; không được đọc ngược
    # `chunk.headers` của một chặng phía sau.
    heading_roles: dict[int, str] = Field(default_factory=dict)

    # Nhãn của block văn bản. Rỗng thì mọi paragraph đều role = null, chặng vẫn
    # chạy và vẫn tách được bảng - chỉ là không có ngữ nghĩa nào được gán.
    roles: list[RoleCfg] = Field(default_factory=list)

    # Bỏ dấu nhấn mạnh trong ô tiêu đề bảng: "**Tên cột**" -> "Tên cột".
    strip_cell_emphasis: bool = True

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
class SplitRule(BaseModel):
    """Một bậc trong thang cắt. Thứ tự trong `split_on` LÀ thứ tự ưu tiên.

    Bậc đầu cắt theo cấu trúc; chỉ khi chunk vẫn vượt ngân sách mới xuống bậc
    sau. Nhờ vậy tài liệu có ranh giới rõ không bao giờ bị cắt giữa chừng, còn
    tài liệu có bảng khổng lồ vẫn không sinh ra chunk quá dài.
    """

    by: Literal["heading", "table_row", "length"]

    level: int | None = None       # heading: cấp nào là một đơn vị nội dung
    group: int = 10                # table_row: bao nhiêu hàng một mảnh
    repeat_header: bool = True     # table_row: lặp hàng tiêu đề vào mỗi mảnh

    # length: ranh giới thử lần lượt, từ TO tới NHỎ. Dấu ngăn bị XOÁ khỏi nội
    # dung sau khi cắt (giống `Delimiter` của Dify). Đặt cứng trong code là giả
    # định văn xuôi: tài liệu code cần ["\nclass ", "\ndef "], văn bản pháp
    # quy cần ["\nĐiều ", "\nKhoản "], log hội thoại cần cắt theo lượt nói.
    separators: list[str] = Field(
        default_factory=lambda: ["\n\n", "\n", ". ", " ", ""]
    )

    model_config = {"extra": "forbid"}


class BudgetCfg(BaseModel):
    """Ngân sách độ dài của một chunk.

    `unit: token` đếm bằng CHÍNH tokenizer của `embed.dense.model`, không phải
    một xấp xỉ. Đây là lý do không có khoá `tokenizer` riêng: ngân sách chỉ có
    nghĩa khi nó nói cùng ngôn ngữ với cái model sẽ đọc chunk.
    """

    unit: Literal["token", "char"] = "token"
    max: int = 1024
    min: int = 120
    overlap: int = 0
    # Vượt trần: `descend` xuống bậc cắt sau, `keep` giữ nguyên và cảnh báo.
    on_overflow: Literal["descend", "keep"] = "descend"
    # Hụt sàn: `keep` giữ và cảnh báo, `drop` bỏ hẳn chunk.
    on_underflow: Literal["keep", "drop"] = "keep"

    model_config = {"extra": "forbid"}

    @model_validator(mode="after")
    def _check(self):
        if self.min >= self.max:
            raise ValueError("chunk.budget.min phải nhỏ hơn chunk.budget.max")
        if self.overlap >= self.max:
            raise ValueError("chunk.budget.overlap phải nhỏ hơn chunk.budget.max")
        return self


class FilterCfg(BaseModel):
    """Element nào không được đụng vào, chunk nào bị bỏ."""

    # Modality không bao giờ bị cắt nhỏ dù vượt ngân sách.
    atomic_modalities: list[str] = Field(default_factory=list)
    drop_empty: bool = True

    model_config = {"extra": "forbid"}


class BreadcrumbCfg(BaseModel):
    """Đường dẫn tiêu đề prepend vào text trước khi embed."""

    enabled: bool = True
    separator: str = " > "
    include_doc_title: bool = True

    model_config = {"extra": "forbid"}


class InheritCfg(BaseModel):
    """Ngữ cảnh mà các mảnh sau của một đơn vị thừa hưởng từ mảnh đầu.

    Bảng bị cắt làm ba thì mảnh 2 và 3 mất câu "Ý nghĩa của bảng: ..." - đứng
    một mình chúng chỉ còn là lưới ô, không truy hồi được. `from_roles` khai
    role nào mang ngữ cảnh đó.
    """

    from_roles: list[str] = Field(default_factory=list)
    max_chars: int = 300

    model_config = {"extra": "forbid"}


class ContextCfg(BaseModel):
    breadcrumb: BreadcrumbCfg = Field(default_factory=BreadcrumbCfg)
    inherit: InheritCfg = Field(default_factory=InheritCfg)
    # Dựng lại nhãn `strip_label` đã cắt: "Ý nghĩa của bảng:" là ngữ cảnh thật.
    restore_labels: bool = True

    model_config = {"extra": "forbid"}


class ParentCfg(BaseModel):
    """Tầng CHA của chế độ parent-child.

    Con dùng để KHỚP truy vấn (nhỏ nên vector đặc trưng, khớp chính xác), cha
    được TRẢ VỀ cho LLM (lớn nên đủ ngữ cảnh để trả lời). Không có nó thì phải
    chọn một trong hai: khớp chính xác mà thiếu ngữ cảnh, hoặc ngược lại.
    """

    # paragraph  cắt cha theo `split_on`/`budget` riêng của tầng cha
    # full_doc   cả tài liệu là MỘT cha, cắt cụt ở `max_tokens`
    method: Literal["paragraph", "full_doc"] = "paragraph"

    split_on: list[SplitRule] = Field(default_factory=list)
    budget: BudgetCfg = Field(default_factory=BudgetCfg)

    # Chỉ dùng cho `full_doc`, đo bằng đúng `budget.unit` của tầng cha. Dify cố
    # định 10.000 token; ở đây theo đơn vị bạn khai. Cha quá dài thì vô dụng:
    # nhét cả tài liệu vào prompt vừa tốn vừa làm loãng phần thật sự liên quan.
    max_length: int = 10000

    model_config = {"extra": "forbid"}

    @model_validator(mode="after")
    def _check(self):
        if self.method == "paragraph" and not self.split_on:
            raise ValueError("chunk.parent.method='paragraph' thì phải khai parent.split_on")
        return self


class ChunkCfg(BaseModel):
    """IR -> chunk. Thang cắt + ngân sách + ngữ cảnh.

    Hai chế độ, theo đúng cách Dify chia:

        general       cắt phẳng, mọi chunk cùng một bộ tham số, khớp cái nào
                      trả thẳng cái đó.
        parent_child  hai tầng. `split_on`/`budget` ở đây là cách cắt CON;
                      khối `parent` là cách dựng cha.
    """

    mode: Literal["general", "parent_child"] = "general"

    split_on: list[SplitRule] = Field(default_factory=list)
    budget: BudgetCfg = Field(default_factory=BudgetCfg)
    parent: ParentCfg | None = None

    # parent_child: tầng CON chỉ giữ element có role trong danh sách này; rỗng
    # là giữ tất cả. Đây là chỗ khai "khớp bằng câu hỏi, trả về cả hàng": con
    # chỉ gồm `sample_query` nên vector của nó thuần câu hỏi, không bị pha loãng
    # bởi evidence và SQL - còn cha vẫn là cả mẫu.
    child_roles: list[str] = Field(default_factory=list)
    filter: FilterCfg = Field(default_factory=FilterCfg)
    context: ContextCfg = Field(default_factory=ContextCfg)

    model_config = {"extra": "forbid"}

    @model_validator(mode="after")
    def _check(self):
        if not self.split_on:
            raise ValueError("chunk.split_on phải có ít nhất một bậc")
        if self.mode == "parent_child" and self.parent is None:
            raise ValueError("chunk.mode='parent_child' thì phải khai khối chunk.parent")
        # Chốt chặn chỉ cần khi thang THẬT SỰ đi xuống. `on_overflow: keep` là
        # kịch bản "cắt theo cấu trúc, kệ độ dài" - ở đó `length` là thừa.
        if self.budget.on_overflow == "descend" and self.split_on[-1].by != "length":
            raise ValueError(
                "budget.on_overflow='descend' thì bậc cuối của chunk.split_on phải "
                "là 'length', nếu không chunk vượt trần không còn cách nào cắt nhỏ. "
                "Muốn cắt thuần theo cấu trúc thì đặt on_overflow='keep'."
            )
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
    collection: str                      # chunk tài liệu tri thức
    # Chunk SQL sample. Để riêng chứ không dùng chung một collection + filter:
    # IDF của BM25 tính trên toàn collection, trộn hai loại văn bản rất khác nhau
    # vào một chỗ làm lệch trọng số từ khoá của cả hai.
    sql_collection: str | None = None
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


# ---- knowledge ------------------------------------------------------------
class KnowledgeCfg(BaseModel):
    """Một BỘ TRI THỨC: một nguồn, một cách cắt, thuộc một hoặc nhiều dự án.

    Đây là đơn vị khai báo của platform. Hai tài liệu khác nhau được quyền khai
    cách xử lý khác nhau mà không phải tách profile: tài liệu schema cắt theo
    heading, còn bộ SQL sample cắt parent-child với con là câu hỏi và cha là cả
    hàng. Nhét cả hai vào một khối `chunk` duy nhất thì một trong hai phải chịu
    cấu hình của cái kia.

    `project` nhận số hoặc danh sách số, nên một bộ tri thức vừa dùng riêng vừa
    dùng chung được: tài liệu .docx thuộc dự án 1, .pdf thuộc dự án 2, còn bộ
    SQL sample khai `[1, 2]` và được index vào cả hai. Chép làm hai bản thì hai
    bản sẽ lệch nhau, và không có gì báo.
    """

    id: str                              # định danh trong profile, vào payload
    source: str                          # tên file trong `raw_dir`
    project: int | list[int]

    # Tên collection, có thể chứa `{project}`. Dùng chung một bộ tri thức cho
    # nhiều dự án nghĩa là KHAI một lần rồi VẬT CHẤT HOÁ thành nhiều bản, không
    # phải trỏ chung vào một kho: hai dự án là hai hộp đen, không được đọc trúng
    # cùng một collection. Hiện không lộ gì chỉ vì nội dung tình cờ giống nhau
    # là may mắn, không phải bảo đảm.
    collection: str

    # Cắt riêng. Bỏ trống thì dùng khối `chunk` mặc định của profile.
    chunk: "ChunkCfg | None" = None

    model_config = {"extra": "forbid"}

    @property
    def projects(self) -> list[int]:
        return [self.project] if isinstance(self.project, int) else list(self.project)

    def collection_for(self, project: int) -> str:
        """Collection của bộ tri thức này TRONG một dự án."""
        if project not in self.projects:
            raise ValueError(f"bộ tri thức '{self.id}' không thuộc dự án {project}")
        return self.collection.format(project=project)

    @model_validator(mode="after")
    def _cach_ly(self):
        if len(self.projects) > 1 and "{project}" not in self.collection:
            raise ValueError(
                f"bộ tri thức '{self.id}' thuộc {len(self.projects)} dự án nhưng "
                f"collection '{self.collection}' cố định - hai dự án sẽ dùng chung "
                "một kho vật lý. Đặt tên có '{project}', ví dụ 'sqlp{project}__sql'."
            )
        return self


# ---- profile --------------------------------------------------------------
class KBConfig(BaseModel):
    """Một bộ tài liệu và toàn bộ cách xử lý nó."""

    kb: str
    # Dự án đang chạy, đặt bằng `VI_COZE_PROJECT`. Artifact và collection tách
    # hẳn theo nó: dự án 1 đọc .docx, dự án 2 đọc .pdf, hai bên là hai hộp đen
    # và không có đường nào nhìn thấy dữ liệu của nhau.
    project: int | None = None
    name: str
    description: str = ""

    parse: ParseCfg
    knowledge: list[KnowledgeCfg] = Field(default_factory=list)
    extract: ExtractCfg = Field(default_factory=ExtractCfg)
    link: LinkCfg = Field(default_factory=LinkCfg)
    chunk: ChunkCfg
    embed: EmbedCfg
    index: IndexCfg
    retrieval: RetrievalCfg = Field(default_factory=RetrievalCfg)

    model_config = {"extra": "forbid"}

    @model_validator(mode="after")
    def _bac_heading_khop_extract(self):
        """Cấp heading dùng để cắt phải là cấp mà `extract` có gán vai trò.

        Hai khoá này ở hai chặng khác nhau nên rất dễ lệch: sửa
        `extract.heading_roles` thành `{1: section, 3: table}` mà quên
        `chunk.split_on` thì chunker im lặng cho ra 0 chunk.
        """
        for rule in self.chunk.split_on:
            if rule.by == "heading" and rule.level not in self.extract.heading_roles:
                raise ValueError(
                    f"chunk.split_on cắt ở heading cấp {rule.level} nhưng "
                    f"extract.heading_roles chỉ khai {sorted(self.extract.heading_roles)}"
                )
        return self

    # ---- đường dẫn: suy từ `kb`, không lưu trong JSON để profile không dính
    # đường dẫn tuyệt đối của máy nào cả
    @property
    def root(self) -> Path:
        return ROOT

    @property
    def raw_dir(self) -> Path:
        return DATA_DIR / "raw" / self.kb

    def knowledge_of(self, project: int) -> list[KnowledgeCfg]:
        """Các bộ tri thức thuộc một dự án, theo thứ tự khai báo."""
        return [k for k in self.knowledge if project in k.projects]

    def chunk_of(self, knowledge: KnowledgeCfg) -> ChunkCfg:
        """Cách cắt của một bộ tri thức, rơi về mặc định của profile nếu không khai."""
        return knowledge.chunk or self.chunk

    @property
    def projects(self) -> list[int]:
        return sorted({p for k in self.knowledge for p in k.projects})

    @property
    def processed_dir(self) -> Path:
        """Artifact tách theo dự án; nguồn và bộ đo dùng chung."""
        base = DATA_DIR / "processed" / self.kb
        return base / f"p{self.project}" if self.project is not None else base

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
        # Dự án đang chạy quyết định thư mục artifact và tên collection, nên nó
        # phải được biết NGAY lúc nạp - mọi hằng số đường dẫn suy ra từ đây.
        if (project := os.getenv("VI_COZE_PROJECT")) is not None:
            cfg.project = int(project)
        elif cfg.project is None and cfg.knowledge:
            cfg.project = cfg.projects[0]
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

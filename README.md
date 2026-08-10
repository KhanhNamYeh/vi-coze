# vi-coze

Pipeline RAG cho tài liệu mô tả schema database, tiếng Việt.

```
OFFLINE  .docx → markdown → chunk → embed (dense + BM25) → Qdrant
ONLINE   query → hybrid retrieval → RRF → cross-encoder rerank → top-k chunk
```

Không gọi LLM ở bất kỳ đâu — đây là tầng truy hồi, dừng ở việc trả về chunk liên
quan. Phần sinh câu trả lời và tầng SQL chưa nằm trong repo.

Báo cáo kỹ thuật đầy đủ, giải thích từng tham số: [report.md](report.md).

## Bắt đầu

```bash
uv sync
cp .env.example .env
docker compose up -d                 # Qdrant

uv run python -m src.offline_sql "Mô tả bảng BĐS (NEW).docx"
uv run python -m src.online_sql "Bảng nào lưu doanh thu tài khoản chính?"
```

Repo có sẵn tài liệu mẫu trong `data/uploads/sql/docs/` nên clone về chạy được
ngay. Lần chạy đầu tải ~4,4 GB model từ HuggingFace (embedding 2,2 GB + reranker
2,2 GB), chạy CPU.

> Pipeline bám vào cấu trúc của đúng tài liệu mẫu này — tên bảng trong đó dùng
> style `normal` chứ không phải Heading, nên `restructure()` trong
> `src/retrieval/parse.py` phải nhận diện bằng regex. Tài liệu định dạng khác
> cần sửa quy tắc đó, nếu không sẽ ra 0 chunk (có cảnh báo).

## Cấu trúc

```
pyproject.toml
uv.lock
.python-version               # 3.12 — markitdown kéo onnxruntime, chưa có wheel cp314
docker-compose.yml            # postgres + qdrant (chưa dùng)

src/
├── schemas.py                # ChunkMeta: hợp đồng metadata của chunk
├── config_sql.py            # đường dẫn + mọi tham số
├── offline.py               # pipeline đầy đủ                 [chạy được]
└── retrieval/
    ├── parse.py             # docs -> .md                     [chạy được]
    ├── chunking.py          # .md  -> .chunks.jsonl           [chạy được]
    ├── embeddings.py        # dense, dùng chung index+query
    ├── sparse.py            # BM25, dùng chung index+query
    ├── store.py             # embed + upsert Qdrant           [chạy được]
    └── retriever.py         # hybrid search                   [chạy được]

data/
├── uploads/sql/docs/         # file gốc
└── artifacts/sql/docs/       # .md và .chunks.jsonl sinh ra

skills/                       # tài liệu tham chiếu cho agent coding
tests/                        # (trống)
```

## Chạy

```bash
uv sync
docker compose up -d          # Qdrant

# cả luồng: parse -> chunk -> embed -> upsert Qdrant
uv run python -m src.offline "Mô tả bảng BĐS (NEW).docx"

# dừng ở chunk, không nạp model 2,2 GB — dùng khi tune chunking (~10 giây)
uv run python -m src.offline "Mô tả bảng BĐS (NEW).docx" --no-index

# hoặc từng bước
uv run python -m src.retrieval.parse     "Mô tả bảng BĐS (NEW).docx"
uv run python -m src.retrieval.chunking  mo_ta_bang_bds_new.md
uv run python -m src.retrieval.store     mo_ta_bang_bds_new.chunks.jsonl
uv run python -m src.retrieval.retriever "bảng nào lưu doanh thu TKC"
```

**Chỉ cần nhập tên file.** Thư mục mặc định lấy từ `src/config_sql.py`:

| | Mặc định |
|---|---|
| `UPLOAD_DIR` (input của parse) | `data/uploads/sql/docs/` |
| `ARTIFACT_DIR` (output, và input của chunking) | `data/artifacts/sql/docs/` |

Đổi bộ tài liệu khác thì sửa một dòng `KB = "sql/docs"` trong `config_sql.py`.
Muốn trỏ file ngoài thư mục mặc định thì truyền đường dẫn có `/`, tính từ gốc
repo. Gõ sai tên file thì chương trình in ra danh sách file có sẵn.

Nhiều file thì truyền nhiều tên — `offline.py` gọi `.batch()`, không phải vòng
`for` gọi `.invoke()`:

```bash
uv run python -m src.offline "file_a.docx" "file_b.docx"
```

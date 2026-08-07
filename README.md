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

# đặt tài liệu của bạn vào đây
cp <tài-liệu>.docx data/uploads/sql/docs/

uv run python -m src.offline_sql "<tài-liệu>.docx"
uv run python -m src.online_sql "câu hỏi của bạn"
```

Lần chạy đầu tải ~4,4 GB model từ HuggingFace (embedding 2,2 GB + reranker
2,2 GB), chạy CPU.

> **Repo không kèm tài liệu mẫu.** `data/uploads/` và `data/artifacts/` bị
> gitignore. Pipeline hiện bám vào cấu trúc một tài liệu cụ thể (xem
> `restructure()` trong `src/retrieval/parse.py`) — tài liệu khác định dạng sẽ
> cần sửa quy tắc nhận diện tiêu đề ở đó.

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

Repo chạy ở chế độ non-package (`[tool.uv] package = false`) — gọi bằng
`python -m src.<...>` từ gốc repo, không cài vào site-packages.

## offline.py

Nối hai bước bằng LCEL, mỗi bước là một `Runnable` có tên:

```python
RunnableLambda(_parse, name="parse") | RunnableLambda(_chunk, name="chunk")
```

Nhờ vậy `.batch()`, `.stream()` và tracing dùng được ngay mà không phải sửa các
bước; sau này bọc vào worker cũng không phải viết lại. Đơn vị dữ liệu chảy trong
chain là `langchain_core.documents.Document` — đúng thứ mà `store.add_documents()`
nhận, nên nối tiếp embed/store không phải chuyển đổi kiểu.

Luồng đầy đủ, hai bước cuối còn thiếu:

```
parse -> chunk -> [embed] -> [store]
```

## parse.py

`markitdown` lo phần nặng (đọc docx, giữ nguyên bảng). Ba việc còn lại phải tự
làm vì không thư viện nào biết:

1. **Bỏ mục lục** — markitdown xuất mục lục thành 28 dòng link
   `[...](#_heading=...)`. Bỏ toàn bộ phần trước heading đầu tiên.
2. **Dựng lại cấp bậc tiêu đề.** Trong docx nguồn, 7 dòng nhóm nghiệp vụ là
   `Heading 1` nhưng 18 dòng tên bảng lại là style `normal` — y hệt đoạn văn
   thường. markitdown vì thế cho ra `* 1. **Bảng X**`, và splitter sẽ chỉ cắt
   được thành 7 chunk theo nhóm, mỗi chunk gộp 4–6 bảng. Quy tắc nâng lên
   `## Bảng X` là quy tắc nghiệp vụ, đúng 18/18.
3. **Unescape `\_`** — 427 chỗ. `USER\_NAME` làm bẩn cả text đem đi embed lẫn
   `table_name` trích ra sau này.

Sau đó `sanitize()`: NFC, bỏ ký tự vô hình, bỏ HTML sót, chặn câu mệnh lệnh
nhắm vào model. Đây là **ranh giới tin cậy** — qua hàm này, nội dung tài liệu là
*dữ liệu*, không phải chỉ thị.

## chunking.py

`MarkdownHeaderTextSplitter` cắt trên `#` (nhóm) và `##` (bảng). **Một bảng = một
chunk, overlap = 0** — ranh giới `##` là ranh giới ngữ nghĩa do người viết tài
liệu đặt, không phải máy đoán, nên không có gì bị cắt ngang câu. Tham số ở
`config_sql.py`.

```
18 chunk | min=465 p50=1112 max=3498 ký tự | có table_name: 18/18
```

`table_name` là trường quan trọng nhất ngoài vector — sau này nó là chỗ lấy
allowlist bảng cho SQL tool.

## Embedding và lưu trữ

| | |
|---|---|
| Dense | `AITeamVN/Vietnamese_Embedding` (fine-tune từ bge-m3), 1024 chiều, trần 2048 token |
| Sparse | `Qdrant/bm25`, `disable_stemmer=True`, `avg_len=96` |
| Collection | `sqldocs__vnemb_1024__c1` — mang theo model + số chiều + version chunking |
| Point ID | `uuid5(NAMESPACE, "doc_id\|no\|part")` — Qdrant chỉ nhận uint64/UUID |

Hai tham số BM25 đo trên chính corpus này, không để mặc định:

- `disable_stemmer=True` — snowball chỉ có 18 ngôn ngữ, **không có tiếng Việt**;
  stemmer tiếng Anh sẽ cắt sai cả từ thường lẫn định danh SQL.
- `avg_len=96` — đo thật (min 60, p50 98, max 146 token). Mặc định fastembed là
  256, sai gần 3 lần, làm lệch phần chuẩn hoá độ dài của BM25.

Dense và sparse nằm **cùng một collection** dưới hai vector có tên, query một
lần rồi Qdrant fuse bằng RRF. Tách hai store là tự chuốc lệch dữ liệu khi
re-index. IDF để `Modifier.IDF` cho Qdrant tự tính trên toàn collection — tính
sẵn lúc index thì mỗi lần nạp thêm tài liệu là IDF cũ đi.

Đổi embedding model = đổi không gian vector: phải index lại toàn bộ **và** đổi
tên collection. `ensure_collection()` ném lỗi nếu số chiều không khớp, thay vì
lặng lẽ ghi vector sai không gian.

## retriever.py

Hybrid: lấy dư 20 mỗi nhánh rồi RRF chọn lại. Chỉ search — không gọi LLM.

Hybrid đáng giá ở corpus này vì query hay chứa định danh SQL. Ví dụ query
`"V_BDS_SITE"`:

| | Hạng 1 | Hạng 2 | Hạng 3 |
|---|---|---|---|
| dense | V_BDS_SITE `0.470` | V_BDS_NEW_SUB_SHOP `0.386` | V_BDS_NEW_SUB_SALE_POINT `0.385` |
| sparse | V_BDS_SITE `1.647` | — | — |

Dense xếp ba bảng `V_BDS_*` gần bằng điểm nhau — suýt lẫn. Sparse tách bạch hẳn.

## Còn thiếu

- **Không có test nào** — `tests/` rỗng. `restructure()` trong `parse.py` là regex
  bám vào format docx cụ thể; tài liệu mới sai format sẽ vỡ im lặng.
- **Không có eval retrieval** (recall@k / MRR). Không có nó thì đổi `avg_len`,
  `k`, hay tham số chunking là đoán, không đo được.
- `print` thay vì `logging`; chưa có `.env` loader.
- Ước lượng token/chunk vẫn tính theo tỷ lệ ký tự, chưa đo bằng tokenizer thật
  của embedding model (trần 2048 còn dư nhiều nên chưa gấp).

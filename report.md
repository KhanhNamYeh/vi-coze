# Báo cáo kỹ thuật — pipeline RAG cho schema database

Tài liệu này đi theo đúng đường dữ liệu chạy, từ file `.docx` gốc tới top-5 chunk
trả về. Mỗi tham số đều ghi giá trị, nguồn gốc (đo được hay đặt tay), và hệ quả
khi đổi.

Số liệu đo trên tài liệu `Mô tả bảng BĐS (NEW).docx`, ngày 2026-08-07.

---

## 0. Tổng quan

```
OFFLINE  (src/offline_sql.py)
  .docx ──markitdown──> md thô ──restructure──> md có cấu trúc ──sanitize──> md sạch
        ──MarkdownHeaderTextSplitter──> 18 chunk
        ──┬─ dense  (Vietnamese_Embedding, 1024d) ─┬──> Qdrant collection
          └─ sparse (BM25)                        ─┘

ONLINE   (src/online_sql.py)
  query ──┬─ dense retriever  (20 ứng viên) ─┬── RRF k=40 ──> rerank ──> top 5
          └─ sparse retriever (20 ứng viên) ─┘   (client)     (cross-encoder)
```

Ranh giới: **offline không cần API, online không gọi LLM.** Cả hai luồng dùng
chung `embeddings.py` và `sparse.py` — nếu tách đôi, index và query sẽ lệch model
hoặc lệch tham số mà không có lỗi nào báo.

### Môi trường

| Thành phần | Version |
|---|---|
| Python | 3.12 (ghim `<3.14`: onnxruntime chưa có wheel cp314) |
| Qdrant | 1.19.0 (docker, `qdrant/qdrant:latest`) |
| torch | 2.13.0 — bản CPU-only qua index `pytorch-cpu` |
| transformers / sentence-transformers | 5.14.1 / 5.7.0 |
| langchain-core / -text-splitters / -classic / -huggingface | 1.5.3 / 1.1.2 / 1.0.8 / 1.2.2 |
| qdrant-client / fastembed | ≥1.12 / 0.8.0 |
| markitdown | 0.1.7 |

`.venv` 924 MB. Không cài repo như package (`[tool.uv] package = false`), chạy
bằng `python -m src.<module>`.

---

## 1. Đầu vào

| | |
|---|---|
| File | `data/uploads/sql/docs/Mô tả bảng BĐS (NEW).docx` |
| Kích thước | 223.974 byte |
| Cấu trúc | 196 đoạn văn, 18 bảng, 1 khối `sdt` (mục lục), 7 `Heading 1` |
| Nội dung | 18 bảng/view Oracle, mỗi khối gồm: tên bảng → ý nghĩa → bảng cột → mối liên kết → ghi chú |

Trong 18 "bảng" có **3 cái không phải bảng** mà là Oracle pipelined function:
`TABLE(pck_report_chatbox.get_*_by_precinct(:date, :user_name))`. Chúng nhận
tham số bind, nên tầng SQL sau này phải xử lý khác bảng thường.

---

## 2. Parse — `src/retrieval/parse.py`

### 2.1 Convert

`markitdown` đọc `.docx`, giữ nguyên bảng dưới dạng markdown table. Ba việc
markitdown **không** làm được, phải xử lý thêm:

| Vấn đề | Đo được | Cách xử lý |
|---|---|---|
| Mục lục lọt vào output | 28 dòng `[...](#_heading=...)` | Bỏ toàn bộ phần trước heading `#` đầu tiên |
| Tên bảng không phải Heading | 7 dòng `#`, **0 dòng `##`** | Nâng `* 1. **Bảng X**` → `## Bảng X` |
| Escape ký tự | 427 chỗ `\_` | Unescape `\\([_*\[\]()#+\-.!\`])` |

**Điểm quan trọng nhất của cả pipeline nằm ở dòng thứ hai.** Trong docx nguồn, 7
dòng nhóm nghiệp vụ dùng style `Heading 1`, nhưng 18 dòng tên bảng dùng style
`normal` — giống hệt đoạn văn thường. Không converter nào đoán được chúng là tiêu
đề. Nếu để nguyên, splitter chỉ cắt được thành **7 chunk theo nhóm**, chunk lớn
nhất gộp 6 bảng khác nhau — hỏi về `LOCATION_GROUP` sẽ trả về cục có cả `PROJECT`,
`V_MAN_TASK`, `V_CAT_STAFF`.

Quy tắc khôi phục là quy tắc nghiệp vụ, khớp **18/18**:

```python
TABLE_HEADING = re.compile(r"^\*\s+\d+\.\s+\*\*Bảng\s+(?P<name>.+?)\*\*\s*$")
```

`\d+\.` là bắt buộc: nó phân biệt dòng tên bảng với 3 dòng ghi chú cũng in đậm
(`* **Bảng này đã có sẵn phân quyền...**`).

### 2.2 Sanitize

| Bước | Tham số | Lý do |
|---|---|---|
| Chuẩn hoá unicode | NFC | Tiếng Việt có dạng tổ hợp dấu; NFD làm lệch cả token lẫn `content_hash` giữa hai lần chạy |
| Bỏ ký tự vô hình | `U+200B–200F`, `202A–202E`, `2060–2064`, `FEFF`, `00AD` | Zero-width, BOM, soft hyphen, bidi |
| Bỏ HTML sót | thẻ ≤200 ký tự + comment | |
| Chặn câu mệnh lệnh | 5 mẫu regex | **Hạn chế lớn — xem §9** |
| Sửa header gõ sai | `Cột\d+` → `Tên cột` | 1 chỗ trong tài liệu; để nguyên thì "Cột2" thành token rác |
| Gộp khoảng trắng | chỉ giữa chữ (`(?<=\S)`) | Thụt đầu dòng là cú pháp markdown, không được đụng |

### 2.3 Kết quả

| | |
|---|---|
| Output | `data/artifacts/sql/docs/mo_ta_bang_bds_new.md` |
| Kích thước | 26.474 byte (~21.811 ký tự) |
| Cấu trúc | 7 `#` (nhóm) + 18 `##` (bảng) |
| `doc_id` | `mo_ta_bang_bds_new` (slugify: bỏ dấu, `đ`→`d`, non-alnum→`_`) |

Có chốt chặn: markdown < 50 ký tự thì ném lỗi (dấu hiệu PDF scan chưa OCR);
0 heading `##` thì cảnh báo.

---

## 3. Chunking — `src/retrieval/chunking.py`

### 3.1 Chiến lược

**Một bảng = một chunk, overlap = 0.** Không dùng fixed-size splitter.

Ranh giới `##` là ranh giới ngữ nghĩa do người viết tài liệu đặt, không phải máy
đoán — không có gì bị cắt ngang câu, nên overlap chỉ tạo trùng lặp làm nhiễu
top-k. Đơn vị truy vấn (một bảng) trùng đơn vị tài liệu.

Nếu cắt theo độ dài: p50 chỉ 1.112 ký tự, một chunk 512 token (~1.200–1.500 ký
tự) sẽ rơi vào giữa bảng markdown — nửa số cột nằm ở chunk sau, mất dòng header,
`| USER_ID | NUMBER | Mã định danh |` không còn biết thuộc bảng nào.

### 3.2 Tham số

| Tham số | Giá trị | Nguồn |
|---|---|---|
| `splitter` | `MarkdownHeaderTextSplitter` | LangChain |
| `HEADERS_TO_SPLIT_ON` | `[("#","section"), ("##","table")]` | cấu trúc tài liệu |
| `STRIP_HEADERS` | `False` — giữ dòng tiêu đề trong chunk | |
| `CHUNK_OVERLAP` | `0` | ranh giới ngữ nghĩa |
| `MAX_CHARS` | `6000` | lưới cảnh báo thô, không cần model |
| `MIN_CHARS` | `200` | phát hiện chunk mồ côi |

`check()` tách khỏi `split()` để tune tham số không phải chạy lại cả pipeline.
Nó **chỉ cảnh báo, không tự sửa**: vượt trần, dưới sàn, hoặc trùng `content_hash`.

### 3.3 Kết quả đo

| Chỉ số | Giá trị |
|---|---|
| Số chunk | **18** |
| Kích thước | min 465 · p50 1.112 · p90 2.764 · max 3.498 ký tự |
| Tổng | 21.840 ký tự |
| Có `table_name` | 18/18 |
| Chunk mồ côi / trùng lặp | 0 |

Phân bố theo nhóm nghiệp vụ:

| Nhóm | Số bảng |
|---|---|
| Danh mục dùng chung | 2 |
| Dữ liệu điểm bán | 4 |
| Dữ liệu kinh doanh | 2 |
| Vùng phủ địa lý | 1 |
| Vùng phủ kỹ thuật | 1 |
| Báo cáo doanh thu TKC và VLR | 2 |
| Quản lý công việc và dự án | 6 |

Đánh số `1.1 … 7.6` khớp chính xác mục lục gốc của tài liệu.

### 3.4 Metadata mỗi chunk

Validate qua `ChunkMeta` (pydantic, `extra="forbid"`) — thêm field sau khi đã
index thì phải index lại toàn bộ.

| Field | Ví dụ | Dùng để |
|---|---|---|
| `doc_id` | `mo_ta_bang_bds_new` | truy nguồn |
| `section` | `Báo cáo doanh thu TKC và VLR` | filter theo nhóm |
| `table_name` | `V_BDS_SITE` | **khoá nối sang tầng SQL** — allowlist bảng lấy từ đây |
| `no` | `5.1` | thứ tự trong tài liệu |
| `part` | `1/1` | đánh dấu khối bị tách (hiện chưa dùng) |
| `n_chars` | `1426` | chẩn đoán |
| `chunk_id` | `sha256(doc_id\|no\|part)[:16]` | tất định |
| `content_hash` | `sha256(text)` | phát hiện trùng, bỏ qua re-embed |
| `source_path` | đường dẫn tương đối | payload không được chứa path máy build |

---

## 4. Embedding dense — `src/retrieval/embeddings.py`

| Tham số | Giá trị | Ghi chú |
|---|---|---|
| `EMBED_MODEL` | `AITeamVN/Vietnamese_Embedding` | fine-tune từ `BAAI/bge-m3` cho tiếng Việt |
| `EMBED_DIM` | `1024` | đã verify khớp bằng probe lúc nạp model |
| `EMBED_MAX_TOKENS` | `2048` | trần của model |
| `EMBED_BATCH` | `16` | |
| `NORMALIZE_EMBEDDINGS` | `True` | cosine similarity cần vector đã chuẩn hoá |
| `QUERY_PREFIX` / `PASSAGE_PREFIX` | `""` / `""` | họ bge-m3 không cần; **họ E5 thì bắt buộc** |

Kích thước model ~2,2 GB, chạy CPU.

### Trần 2048 quyết định có phải tách chunk hay không

| Model cân nhắc | Trần token | Hệ quả |
|---|---|---|
| `intfloat/multilingual-e5-large` | 512 | phải tách 6/18 khối — mất tính "một bảng một chunk" |
| **`AITeamVN/Vietnamese_Embedding`** ← chọn | **2048** | **tách 0/18** |
| `BAAI/bge-m3` | 8192 | tách 0/18, dư thừa |

Khối lớn nhất 3.498 ký tự ≈ 1.160–1.580 token (ước lượng theo tỷ lệ 2,2–3 ký
tự/token) → còn dư 25–45%. **Chưa đo bằng tokenizer thật** — xem §9.

Prefix để rỗng nhưng vẫn giữ trong code: đổi sang model họ E5 thì chỉ sửa config,
không phải sửa chỗ gọi. Thiếu prefix khi model cần là mất điểm số mà không báo lỗi.

---

## 5. Sparse BM25 — `src/retrieval/sparse.py`

| Tham số | Giá trị | Nguồn |
|---|---|---|
| `SPARSE_MODEL` | `Qdrant/bm25` (fastembed) | |
| `BM25_DISABLE_STEMMER` | `True` | **bắt buộc, xem dưới** |
| `BM25_LANGUAGE` | `"english"` | chỉ còn tác dụng chọn stopwords |
| `BM25_AVG_LEN` | `96.0` | **đo trên corpus thật** |
| `BM25_K` | `1.2` | mặc định, bão hoà tần suất từ |
| `BM25_B` | `0.75` | mặc định, mức phạt theo độ dài |

### Hai tham số phải chỉnh khỏi mặc định

**`disable_stemmer=True`.** Snowball chỉ hỗ trợ 18 ngôn ngữ:

```
arabic danish dutch english finnish french german greek hungarian italian
norwegian portuguese romanian russian spanish swedish tamil turkish
```

**Không có tiếng Việt.** Để mặc định thì stemmer tiếng Anh chạy trên text tiếng
Việt và trên định danh SQL viết hoa — cắt sai token, giảm điểm khớp mà không có
lỗi nào báo.

**`avg_len=96.0`, mặc định fastembed là `256`.** Đo trên chính 18 chunk:

| | token BM25 |
|---|---|
| min | 60 |
| p50 | 98 |
| max | 146 |
| trung bình | **96** |

Sai gần 3 lần thì phần chuẩn hoá độ dài (tham số `b`) trong công thức BM25 lệch
theo. Phải đo lại khi corpus đổi đáng kể.

### BM25 không đối xứng

| Hàm | Dùng khi | Nội dung |
|---|---|---|
| `encode_passages()` | index | trọng số tần suất + chuẩn hoá độ dài |
| `encode_query()` | search | chỉ liệt kê term |

Đo thực tế: cùng một cặp, document sinh 7 token có trọng số, query sinh 2 token
với trọng số khác hẳn. Dùng nhầm `encode_passages` cho query là sai công thức mà
vẫn chạy, không báo lỗi.

**IDF không tính ở client.** Collection bật `Modifier.IDF` để Qdrant tính trên
toàn bộ dữ liệu — tính sẵn lúc index thì mỗi lần nạp thêm tài liệu là IDF cũ đi.

---

## 6. Vector store — `src/retrieval/store.py`

### 6.1 Collection

```
sqldocs__vnemb_1024__c1
         │      │      └── CHUNKING_VERSION
         │      └── EMBED_DIM
         └── model
```

Tên mang theo model + số chiều + version chunking. Đổi bất kỳ thành phần nào cũng
phải đổi tên, nếu không vector khác thế hệ lẫn vào nhau trong cùng một chỗ.

| Cấu hình | Giá trị (đọc từ Qdrant) |
|---|---|
| points | 18, status `green` |
| dense | `{"dense": {"size": 1024, "distance": "Cosine"}}` |
| sparse | `{"bm25": {"modifier": "idf"}}` |
| payload index | `doc_id`, `table_name`, `section` — đều `keyword` |

`ensure_collection()` **ném lỗi** nếu số chiều collection ≠ số chiều model, thay
vì lặng lẽ ghi vector sai không gian.

### 6.2 Ba chi tiết bắt buộc

**Point ID phải là uint64 hoặc UUID.** `chunk_id` (hex 16 ký tự) dùng thẳng sẽ bị
Qdrant từ chối. Giải pháp:

```python
NAMESPACE = uuid.UUID("6f9619ff-8b86-d011-b42d-00c04fc964ff")
point_id = uuid5(NAMESPACE, f"{doc_id}|{no}|{part}")
```

Tất định nên upsert lại không nhân đôi — **đã kiểm chứng**: chạy hai lần liên
tiếp, collection vẫn đúng 18 điểm.

**Payload index.** Thiếu thì filter theo `table_name` là quét toàn bộ collection.

**Dense và sparse cùng một collection**, dưới hai vector có tên. Tách hai store là
tự chuốc lệch dữ liệu khi re-index.

### 6.3 Payload

Ngoài metadata của chunk, thêm: `text` (search phải trả nội dung, không chỉ id),
`embed_model`, `sparse_model`.

---

## 7. Luồng online — `src/online_sql.py`

### 7.1 Tham số

| Tham số | Giá trị | Nguồn |
|---|---|---|
| `CANDIDATE_K` | `20` mỗi nhánh | **đặt tay, chưa đo** |
| `RRF_K` | `40` | yêu cầu |
| `RRF_WEIGHTS` | `[0.5, 0.5]` (dense, sparse) | **đặt tay, chưa đo** |
| `RERANK_MODEL` | `AITeamVN/Vietnamese_Reranker` | |
| `RERANK_TOP_N` | `5` | yêu cầu |

### 7.2 Vì sao RRF chạy ở client

`qdrant_client.models.FusionQuery` chỉ có **đúng một field `fusion`** — không có
tham số `k`. Hằng số RRF cố định phía server. Muốn `k=40` thì phải fuse ở client,
và `EnsembleRetriever.c` của LangChain chính là hằng số đó:

```
score(d) = Σ  weight_i / (RRF_K + rank_i(d))
```

Đây là đánh đổi có thật: mất fusion server-side (một round-trip) để đổi lấy quyền
chỉnh `k`.

### 7.3 Thành phần LangChain dùng lại

| Việc | Class | Package |
|---|---|---|
| Bọc `search()` thành retriever | `BaseRetriever` | `langchain-core` |
| Fusion RRF | `EnsembleRetriever(c=40)` | `langchain-classic` |
| Ghép rerank | `ContextualCompressionRetriever` | `langchain-classic` |
| Rerank | `CrossEncoderReranker` | `langchain-classic` |
| Interface cross-encoder | `BaseCrossEncoder` | `langchain-core` |

**Không dùng `langchain-community`** (đang bị sunset). `HuggingFaceCrossEncoder`
nằm ở đó, nhưng `BaseCrossEncoder` lại ở `langchain-core`, nên tự implement bằng
`sentence-transformers` — 8 dòng.

### 7.4 Sửa `CrossEncoderReranker`

Bản gốc của LangChain vứt điểm đi:

```python
result = sorted(docs_with_scores, key=operator.itemgetter(1), reverse=True)
return [doc for doc, _ in result[: self.top_n]]   # score biến mất
```

Không có điểm thì không phân biệt được hit mạnh với hit yếu, cũng không đặt được
ngưỡng cắt. `ScoringReranker` kế thừa và ghi vào `metadata["rerank_score"]`.

### 7.5 Kết quả

Query: `"Bảng nào lưu doanh thu tài khoản chính theo phường xã?"`

| # | rerank_score | Bảng |
|---|---|---|
| 1 | **+0.9333** | `TABLE(pck_report_chatbox.get_rev_data_by_precinct(...))` |
| 2 | +0.0964 | `V_USER_PRECINCT_PERMISSION` |
| 3 | +0.0180 | `TABLE(pck_report_chatbox.get_vlr_data_by_precinct(...))` |
| 4 | +0.0110 | `PRECINCT` |
| 5 | +0.0110 | `V_BDS_SITE` |

Khoảng cách 0.933 → 0.096 (gần 10 lần) cho thấy reranker tách bạch dứt khoát:
hạng 1 đúng là bảng doanh thu theo phường/xã, phần còn lại chỉ là ngữ cảnh phụ.

### 7.6 Hybrid có đáng không

Query `"V_BDS_SITE"` (định danh SQL chính xác):

| | Hạng 1 | Hạng 2 | Hạng 3 |
|---|---|---|---|
| dense | V_BDS_SITE `0.470` | V_BDS_NEW_SUB_SHOP `0.386` | V_BDS_NEW_SUB_SALE_POINT `0.385` |
| sparse | V_BDS_SITE `1.647` | — | — |

Dense xếp ba bảng `V_BDS_*` cách nhau 0.001–0.084 điểm — suýt lẫn. Sparse tách
bạch hẳn. Corpus này đầy định danh SQL nên hybrid có giá trị thật, không phải
thêm cho đủ.

---

## 8. Thời gian chạy

Đo trên máy hiện tại, model đã có trong cache:

| Lệnh | Thời gian | Ghi chú |
|---|---|---|
| `offline_sql --no-index` | **8 giây** | parse + chunk, không nạp model |
| `offline_sql` (đầy đủ) | **62 giây** | phần lớn là nạp model 2,2 GB |
| `online_sql` (1 query) | **82 giây** | nạp cả embedding lẫn reranker |

Gần như toàn bộ thời gian là nạp model, không phải tính toán — 18 chunk là khối
lượng không đáng kể. Khi bọc thành service, model nạp một lần lúc khởi động thì
mỗi query chỉ còn phần inference.

`--no-index` tồn tại chính vì lý do này: tune tham số chunking không cần đụng tới
model.

---

## 9. Hạn chế và những gì chưa kiểm chứng

### Tham số đặt tay, chưa đo

| Tham số | Giá trị | Vấn đề |
|---|---|---|
| `RRF_WEIGHTS` | `[0.5, 0.5]` | Chưa biết `[0.7, 0.3]` có tốt hơn không |
| `CANDIDATE_K` | `20` | Chưa biết 10 có đủ hay 50 có tốt hơn |
| `BM25_K` / `BM25_B` | `1.2` / `0.75` | Mặc định của công thức, chưa tune |

**Nguyên nhân gốc: chưa có eval recall@k / MRR.** Không có nó thì mọi thay đổi
tham số đều là đoán. Đây là việc đáng làm nhất tiếp theo.

### Chưa đo bằng tokenizer thật

Cột "ước lượng token" ở §4 tính theo tỷ lệ 2,2–3 ký tự/token. Định danh SQL viết
hoa (`V_BDS_NEW_SUB_SALE_POINT`) tokenize tệ hơn văn xuôi nên số thật có thể cao
hơn. Trần 2048 còn dư nhiều nên chưa gấp, nhưng nên biết số chính xác.

### Regex chặn prompt injection là phòng thủ hình thức

`INJECTION` trong `sanitize()` chặn 5 chuỗi cố định. Nó **không** cản được
injection thật, mà lại có thể xoá nhầm nội dung hợp lệ — một dòng bắt đầu bằng
`System:` trong tài liệu kỹ thuật là bình thường. Phòng thủ thật nằm ở tầng
prompt và tầng quyền của tool, không phải ở regex lúc ingest. Nên cân nhắc bỏ.

### Không có test

`tests/` rỗng. Chỗ dễ vỡ nhất là `restructure()` trong `parse.py`: nó là regex
bám vào format docx cụ thể. Tài liệu mới đặt tên bảng khác kiểu sẽ cho ra 0 heading
`##`, và pipeline sẽ tạo 0 chunk — có cảnh báo nhưng không có test nào chặn từ đầu.

### Khác

- `print` thay vì `logging` — production không tắt/lọc được theo level.
- Chưa có `.env` loader; chỉ `QDRANT_URL` đọc từ biến môi trường.
- `qdrant/qdrant:latest` chưa ghim version.
- Chưa có Postgres cho sổ ghi trạng thái document (`doc status`, resume) — hiện
  trạng thái chỉ nằm ở file trong `data/artifacts/`.
- 5 khối `main()` gần giống nhau (~60 dòng lặp), gộp được thành một CLI.

---

## 10. Bảng tổng hợp toàn bộ tham số

| Nhóm | Tham số | Giá trị | Đo được? |
|---|---|---|---|
| Chunking | `HEADERS_TO_SPLIT_ON` | `[("#","section"),("##","table")]` | theo cấu trúc tài liệu |
| | `STRIP_HEADERS` | `False` | |
| | `CHUNK_OVERLAP` | `0` | suy ra từ chiến lược |
| | `MAX_CHARS` / `MIN_CHARS` | `6000` / `200` | lưới cảnh báo |
| Dense | `EMBED_MODEL` | `AITeamVN/Vietnamese_Embedding` | |
| | `EMBED_DIM` | `1024` | ✅ verify bằng probe |
| | `EMBED_MAX_TOKENS` | `2048` | theo model |
| | `EMBED_BATCH` | `16` | |
| | `NORMALIZE_EMBEDDINGS` | `True` | |
| | `QUERY_PREFIX` / `PASSAGE_PREFIX` | `""` / `""` | theo họ model |
| Sparse | `SPARSE_MODEL` | `Qdrant/bm25` | |
| | `BM25_DISABLE_STEMMER` | `True` | ✅ snowball không có tiếng Việt |
| | `BM25_LANGUAGE` | `"english"` | chỉ chọn stopwords |
| | `BM25_AVG_LEN` | `96.0` | ✅ đo trên 18 chunk |
| | `BM25_K` / `BM25_B` | `1.2` / `0.75` | mặc định |
| Store | `COLLECTION` | `sqldocs__vnemb_1024__c1` | |
| | `DENSE_VECTOR` / `SPARSE_VECTOR` | `dense` / `bm25` | |
| | distance | `Cosine` | |
| | sparse modifier | `IDF` | |
| | `PAYLOAD_INDEX_FIELDS` | `doc_id`, `table_name`, `section` | |
| Online | `CANDIDATE_K` | `20` | ❌ đặt tay |
| | `RRF_K` | `40` | yêu cầu |
| | `RRF_WEIGHTS` | `[0.5, 0.5]` | ❌ đặt tay |
| | `RERANK_MODEL` | `AITeamVN/Vietnamese_Reranker` | |
| | `RERANK_TOP_N` | `5` | yêu cầu |

---

## Phụ lục — lệnh chạy

```bash
uv sync
docker compose up -d

# offline
uv run python -m src.offline_sql "Mô tả bảng BĐS (NEW).docx"
uv run python -m src.offline_sql "Mô tả bảng BĐS (NEW).docx" --no-index
uv run python -m src.offline_sql "..." --recreate     # dựng lại collection

# từng bước
uv run python -m src.retrieval.parse     "Mô tả bảng BĐS (NEW).docx"
uv run python -m src.retrieval.chunking  mo_ta_bang_bds_new.md
uv run python -m src.retrieval.store     mo_ta_bang_bds_new.chunks.jsonl

# online
uv run python -m src.online_sql
uv run python -m src.online_sql "câu hỏi khác"
uv run python -m src.retrieval.retriever "V_BDS_SITE"   # so dense/sparse/hybrid
```

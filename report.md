# Báo cáo kỹ thuật pipeline truy hồi hiện tại

## 1. Phạm vi tài liệu

Tài liệu này mô tả trạng thái triển khai hiện tại của mã nguồn trong repository. Mọi nội dung bên dưới đều tương ứng với cấu hình, lớp, hàm hoặc luồng xử lý đang có trong code.

Phạm vi hiện tại là pipeline lập chỉ mục và truy hồi tài liệu gồm:

1. Chuyển tài liệu sang Markdown.
2. Chuẩn hóa nội dung.
3. Chia nội dung thành chunk theo cấu trúc heading.
4. Sinh vector dense và sparse BM25.
5. Lưu vector cùng metadata vào Qdrant.
6. Truy hồi dense và sparse.
7. Hợp nhất kết quả bằng Reciprocal Rank Fusion.
8. Xếp hạng lại bằng cross-encoder.

Mã nguồn hiện tại chưa gọi mô hình sinh câu trả lời, chưa sinh câu SQL và chưa thực thi truy vấn SQL. Tên các entry point có hậu tố `sql`, nhưng chức năng được triển khai trong các file này hiện là xử lý và truy hồi tài liệu.

## 2. Thành phần mã nguồn

| File | Trách nhiệm đang được triển khai |
|---|---|
| `branch_sql/config.py` | Khai báo đường dẫn, tên model, tham số chunking, Qdrant và retrieval |
| `src/schemas.py` | Định nghĩa metadata của chunk và cách tạo định danh |
| `src/branch_sql/offline/parse/docx_parse.py` | Chuyển tài liệu sang Markdown và chuẩn hóa nội dung |
| `src/branch_sql/offline/chunk/table_chunker.py` | Chia Markdown theo heading và tạo chunk |
| `src/branch_sql/offline/embed/dense.py` | Sinh embedding dense cho tài liệu và truy vấn |
| `src/branch_sql/offline/embed/sparse.py` | Sinh vector sparse BM25 cho tài liệu và truy vấn |
| `src/branch_sql/offline/index/qdrant_store.py` | Tạo collection và ghi point vào Qdrant |
| `src/branch_sql/online/qdrant_retriever.py` | Truy hồi dense, sparse hoặc hybrid từ Qdrant |
| `src/branch_sql/online/rerank.py` | Xếp hạng lại kết quả bằng cross-encoder |
| `src/branch_sql/offline/pipeline.py` | Điều phối pipeline parse, chunk và index |
| `src/branch_sql/online/pipeline.py` | Điều phối hybrid retrieval và reranking |
| `docker-compose.yml` | Khởi chạy dịch vụ Qdrant cục bộ |

## 3. Cấu hình tập trung

Các tham số chính được khai báo trong `branch_sql/config.py`.

### 3.1. Đường dẫn dữ liệu

- Thư mục tài liệu đầu vào: `data/sql/docs`.
- Thư mục upload: `data/sql/docs/uploads`.
- Thư mục artifact: `data/sql/docs/artifacts`.
- Đường dẫn được chuẩn hóa bằng `Path.resolve()` trước khi sử dụng.

Code có khai báo danh sách phần mở rộng tài liệu gồm DOCX, DOC, PDF, PPTX, XLSX, HTML và HTM. Danh sách này hiện chưa được dùng để chặn đầu vào trong `parse.py`; tài liệu được chuyển đổi trực tiếp thông qua MarkItDown.

### 3.2. Chunking

- Heading cấp một được ánh xạ sang metadata `section`.
- Heading cấp hai được ánh xạ sang metadata `table`.
- Heading được giữ lại trong nội dung chunk.
- Ngưỡng cảnh báo chiều dài tối đa: `6000` ký tự.
- Ngưỡng cảnh báo chiều dài tối thiểu: `200` ký tự.

Hai ngưỡng trên chỉ được dùng để sinh cảnh báo. Code hiện không tự chia tiếp chunk quá dài và không tự gộp chunk quá ngắn.

Biến `CHUNK_OVERLAP` được khai báo bằng `0`, nhưng không được truyền vào bộ chia Markdown hiện tại.

### 3.3. Dense embedding

- Model: `AITeamVN/Vietnamese_Embedding`.
- Kích thước vector cấu hình: `1024`.
- Batch size: `16`.
- Vector được chuẩn hóa.
- Query và passage prefix hiện là chuỗi rỗng.

Biến `EMBED_MAX_TOKENS` được khai báo trong cấu hình nhưng chưa được code truyền vào lớp embedding để áp dụng giới hạn token.

### 3.4. Sparse BM25

- Model: `Qdrant/bm25`.
- `k = 1.2`.
- `b = 0.0`.
- Stemmer bị tắt.
- IDF được Qdrant áp dụng ở cấp collection thông qua `Modifier.IDF`.

Code không lưu hoặc truyền `avg_len` và không truyền tham số ngôn ngữ vào sparse encoder.

### 3.5. Retrieval và reranking

- Số ứng viên mỗi retriever: `20`.
- Trọng số dense và sparse: `0.5 / 0.5`.
- Hằng số RRF phía client: `40`.
- Model rerank: `AITeamVN/Vietnamese_Reranker`.
- Số kết quả sau rerank: `5`.

## 4. Pipeline offline

Entry point của pipeline offline là `src/branch_sql/offline/pipeline.py`.

### 4.1. Chuyển đổi tài liệu

`parse_document()` nhận đường dẫn tài liệu và gọi MarkItDown để chuyển nội dung sang Markdown.

Sau chuyển đổi, code thực hiện các bước chuẩn hóa sau:

- Loại phần mục lục đứng trước heading cấp một đầu tiên.
- Loại liên kết mục lục Markdown.
- Loại dòng phân cách.
- Chuyển mẫu tiêu đề bảng phù hợp regex sang heading cấp hai `## Bảng ...`.
- Bỏ ký hiệu bullet ở một số dòng.
- Giải escape Markdown.
- Chuẩn hóa Unicode về NFC.
- Loại ký tự vô hình, HTML comment và HTML tag.
- Loại một số mẫu câu chỉ dẫn được định nghĩa cố định trong regex `INJECTION`.
- Chuẩn hóa khoảng trắng và số dòng trống liên tiếp.
- Sửa mẫu heading cột phù hợp regex `BAD_HEADER`.

Parser từ chối kết quả có ít hơn `50` ký tự. Nếu không tìm thấy heading cấp hai, parser vẫn trả kết quả nhưng kèm cảnh báo.

Kết quả parse gồm nội dung Markdown và metadata:

- `doc_id`.
- `title`.
- `source_name`.
- Số section.
- Số bảng.
- Danh sách cảnh báo.

Markdown sau chuẩn hóa được ghi vào thư mục artifact.

### 4.2. Chia chunk

`chunk_document()` sử dụng `MarkdownHeaderTextSplitter` với hai cấp heading đã cấu hình.

Mỗi phần chỉ được tạo thành chunk khi metadata có trường `table`. Tên bảng được lấy từ heading cấp hai và bỏ tiền tố `Bảng` nếu có. Số thứ tự `no` tăng dần trong từng section.

Mỗi chunk chứa:

- Nội dung văn bản.
- `doc_id`.
- `section`.
- `table_name`.
- `no`.
- `part`, hiện mặc định là `1/1`.
- `source_path`.
- `n_chars`.
- `chunk_id`.
- `content_hash`.

`chunk_id` là SHA-256 rút gọn từ khóa `doc_id|no|part`. `content_hash` là SHA-256 của nội dung chunk sau khi loại khoảng trắng đầu và cuối.

Schema metadata dùng Pydantic với `extra="forbid"`, vì vậy field ngoài định nghĩa sẽ bị từ chối khi validate.

### 4.3. Kiểm tra chunk

`check_chunks()` sinh cảnh báo cho các trường hợp:

- Không có chunk.
- Chunk dài hơn ngưỡng cấu hình.
- Chunk ngắn hơn ngưỡng cấu hình.
- Nhiều chunk có cùng `content_hash`.

Các cảnh báo không dừng pipeline.

Danh sách chunk được ghi thành JSONL trong thư mục artifact.

### 4.4. Sinh vector và lập chỉ mục

Khi không dùng tùy chọn `--no-index`, pipeline gọi `index()` để:

1. Tạo hoặc kiểm tra collection Qdrant.
2. Chia chunk thành batch.
3. Sinh dense embedding bằng `embed_passages()`.
4. Sinh sparse vector bằng `encode_passages()`.
5. Tạo point ID dạng UUID5 xác định từ `doc_id|no|part`.
6. Upsert vector và payload vào Qdrant.

Point ID xác định giúp việc index lại cùng một chunk ghi đè đúng point thay vì tạo point mới có ID ngẫu nhiên.

## 5. Dense embedding

`src/branch_sql/offline/embed/dense.py` khởi tạo `HuggingFaceEmbeddings` và cache instance bằng `lru_cache`.

Hai đường xử lý được tách riêng:

- `embed_passages()` dùng `embed_documents()` cho nội dung tài liệu.
- `embed_query()` dùng `embed_query()` cho câu truy vấn.

Prefix tương ứng được nối vào văn bản trước khi gọi model; với cấu hình hiện tại cả hai prefix đều rỗng.

## 6. Sparse BM25

`src/branch_sql/offline/embed/sparse.py` dùng `fastembed.SparseTextEmbedding` và cache model bằng `lru_cache`.

### 6.1. Cách mã hóa

- `encode_passages()` gọi API `embed()` cho tài liệu.
- `encode_query()` gọi API `query_embed()` cho truy vấn.
- Kết quả được chuyển sang cấu trúc `Sparse` gồm danh sách `indices` và `values`.

Việc tách đường mã hóa tài liệu và truy vấn giữ đúng giao diện bất đối xứng do thư viện sparse embedding cung cấp.

### 6.2. Cấu hình chiều dài

`BM25_B` hiện bằng `0.0`. Vì vậy thành phần chuẩn hóa theo chiều dài tài liệu bị vô hiệu hóa trong công thức BM25 của sparse encoder.

Hệ quả trực tiếp trong implementation hiện tại:

- Không cần cung cấp độ dài trung bình của corpus cho sparse encoder.
- Không có hằng số `BM25_AVG_LEN` trong cấu hình.
- Không có tham số `avg_len` trong hàm tạo sparse model.
- Thay đổi độ dài trung bình của tập tài liệu không yêu cầu cập nhật một giá trị cấu hình BM25 riêng.

`BM25_K = 1.2` vẫn điều khiển mức bão hòa tần suất từ trong tài liệu.

### 6.3. IDF

Sparse vector được khai báo trong Qdrant với `Modifier.IDF`. Encoder tạo trọng số sparse phía tài liệu và truy vấn; Qdrant áp dụng IDF khi tính điểm dựa trên collection đang lưu.

## 7. Lưu trữ Qdrant

`src/branch_sql/offline/index/qdrant_store.py` kết nối tới URL Qdrant từ biến môi trường `QDRANT_URL`, mặc định là `http://localhost:6333`.

### 7.1. Collection

Tên collection được tạo từ:

- Tiền tố cố định `sqldocs`.
- Kích thước dense embedding.
- Phiên bản chunking.

Collection có hai named vector:

- `dense`: vector kích thước `1024`, khoảng cách cosine.
- `bm25`: sparse vector có `Modifier.IDF`.

Ba payload index kiểu keyword được tạo cho:

- `doc_id`.
- `table_name`.
- `section`.

Nếu collection đã tồn tại, code hiện kiểm tra sự tồn tại và kích thước của dense vector. Code chưa kiểm tra lại cấu hình sparse vector hoặc modifier của collection hiện hữu.

Tùy chọn `recreate=True` xóa collection hiện tại rồi tạo lại trước khi upsert.

### 7.2. Payload

Mỗi point lưu:

- Toàn bộ metadata của chunk.
- Nội dung chunk trong field `text`.
- Tên model dense trong field `embed_model`.
- Tên model sparse trong field `sparse_model`.

## 8. Pipeline online

Entry point của luồng truy hồi kết hợp là `src/branch_sql/online/pipeline.py`.

### 8.1. Hai retriever đầu vào

Code tạo hai instance `QdrantRetriever`:

- Một retriever ở chế độ `dense`.
- Một retriever ở chế độ `sparse`.

Mỗi retriever lấy tối đa số ứng viên bằng `CANDIDATE_K`.

### 8.2. Hợp nhất kết quả

Hai danh sách được đưa vào `EnsembleRetriever` của LangChain với:

- Trọng số bằng nhau.
- Hằng số RRF lấy từ `RRF_K`.

Việc hợp nhất trong `online/pipeline.py` được thực hiện phía client dựa trên thứ hạng, không cộng trực tiếp raw score của dense và sparse.

Ngoài luồng trên, `src/branch_sql/online/qdrant_retriever.py` còn cung cấp chế độ `hybrid` dùng `Prefetch` và `FusionQuery(RRF)` của Qdrant để hợp nhất phía server. Chế độ này được gọi trực tiếp qua `search(mode="hybrid")`; `online/pipeline.py` hiện dùng hai retriever riêng và hợp nhất phía client.

### 8.3. Reranking

Kết quả hợp nhất được chuyển vào `ContextualCompressionRetriever` với `ScoringReranker`.

Reranker:

1. Tạo cặp `(query, page_content)` cho từng tài liệu.
2. Gọi `CrossEncoder.predict()` để tính điểm.
3. Sắp xếp giảm dần theo điểm.
4. Giữ tối đa `RERANK_TOP_N` kết quả.
5. Ghi điểm vào metadata `rerank_score`.

Model cross-encoder cũng được cache bằng `lru_cache`.

## 9. Bộ lọc truy hồi

`search()` và `QdrantRetriever` hiện hỗ trợ bộ lọc tùy chọn theo `section`.

Khi có giá trị `section`, code tạo Qdrant filter với điều kiện keyword match chính xác. Các payload index khác đã được tạo cho `doc_id` và `table_name`, nhưng giao diện retriever hiện chưa nhận hai loại filter này.

## 10. Cách chạy hiện có

### 10.1. Khởi chạy Qdrant

```powershell
docker compose up -d
```

`docker-compose.yml` khai báo một service Qdrant, mở cổng HTTP `6333`, gRPC `6334`, dùng named volume và có healthcheck.

Image hiện được khai báo là `qdrant/qdrant:latest`.

### 10.2. Parse, chunk và index

```powershell
uv run python -m src.branch_sql.offline <ten-tai-lieu>
```

Chỉ tạo artifact mà không ghi Qdrant:

```powershell
uv run python -m src.branch_sql.offline <ten-tai-lieu> --no-index
```

Tạo lại collection trước khi index:

```powershell
uv run python -m src.branch_sql.offline <ten-tai-lieu> --recreate
```

Entry point hỗ trợ nhận nhiều tên tài liệu và xử lý bằng `chain.batch()`.

### 10.3. Chạy retrieval và rerank

```powershell
uv run python -m src.branch_sql.online "<cau-hoi>"
```

CLI in nội dung và metadata của các kết quả sau rerank ra standard output.

### 10.4. So sánh các chế độ retrieval

```powershell
uv run python -m src.branch_sql.online.qdrant_retriever "<cau-hoi>"
```

CLI này lần lượt chạy dense, sparse và hybrid để in kết quả của từng chế độ.

## 11. Hành vi lỗi và kiểm tra hiện tại

- Hàm `require()` phát sinh `FileNotFoundError` khi đường dẫn bắt buộc không tồn tại.
- Parser phát sinh `ValueError` nếu nội dung sau chuẩn hóa quá ngắn.
- Indexer phát sinh `RuntimeError` nếu collection hiện hữu thiếu dense vector được cấu hình hoặc có sai kích thước dense.
- Pipeline offline bắt exception theo từng tài liệu, in trạng thái lỗi và tiếp tục tổng hợp kết quả batch.
- Các tiến trình CLI chủ yếu báo trạng thái bằng `print()`.

## 12. Giới hạn trực tiếp từ implementation hiện tại

- Quy tắc nhận diện cấu trúc trong parser phụ thuộc vào heading và regex tiếng Việt cố định, gồm mẫu `Bảng`.
- Chunker chỉ giữ các phần có metadata `table`.
- Cảnh báo chiều dài không làm thay đổi chunk.
- `CHUNK_OVERLAP` và `EMBED_MAX_TOKENS` mới được khai báo, chưa được áp dụng bởi code xử lý tương ứng.
- Kiểm tra collection hiện hữu chỉ xác thực dense vector, chưa xác thực cấu hình sparse.
- Retriever chỉ mở tham số filter theo `section`.
- Luồng online dừng ở kết quả rerank; chưa có bước sinh câu trả lời hoặc thực thi SQL.

## 13. Tóm tắt BM25 đang triển khai

Phần sparse retrieval hiện có cấu hình tối giản:

- FastEmbed tạo sparse vector.
- Stemmer bị tắt.
- `k = 1.2` giữ cơ chế bão hòa tần suất từ.
- `b = 0.0` bỏ chuẩn hóa chiều dài.
- Không lưu `avg_len`.
- Không truyền cấu hình ngôn ngữ.
- Qdrant áp dụng IDF ở cấp collection.
- Sparse được hợp nhất với dense bằng RRF trước khi rerank.

Đây là mô tả đúng theo luồng code hiện tại, không bao gồm tham số đo thử, dữ liệu mẫu hoặc kiến trúc chưa được triển khai.

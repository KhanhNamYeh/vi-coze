# kb-text2sql

MVP Text-to-SQL tiếng Việt dùng hai split dữ liệu độc lập:

- `data/dev`: BIRD dev tiếng Việt gồm 1.534 câu, 11 SQLite database, schema metadata, business context và gold SQL.
- `data/test`: hai bộ dữ liệu cũ dùng làm regression test, giữ business document, SQL dump và gold SQL.

`data` chỉ chứa source data. Markdown trung gian, SQLite tạo từ dump, artifact offline và kết quả đánh giá nằm trong `.runtime`; Docker gắn thư mục này bằng `tmpfs` nên không lưu cache sau khi container dừng.

Gold của `data/dev` chỉ dành cho evaluator và không được index làm retrieval example. Đây là ranh giới bắt buộc để tránh rò rỉ đáp án trên dev.

```text
data/
├── dev/
│   ├── business/
│   ├── dev_databases/
│   ├── gold/
│   ├── dev.json
│   ├── dev.sql
│   └── dev_tables.json
└── test/
    ├── business/
    ├── gold/
    └── sql/
```

## Chạy bằng Docker

```bash
cp .env.example .env
docker compose up --build -d
```

Compose mặc định dùng NVIDIA GPU. Máy cần NVIDIA Container Toolkit/Docker Desktop GPU support; image dùng PyTorch CUDA 12.8, phù hợp driver NVIDIA hỗ trợ CUDA 12.8 trở lên.

- API: <http://localhost:8000>
- Swagger: <http://localhost:8000/docs>
- Gradio UI: <http://localhost:8000/ui>
- Qdrant dashboard: <http://localhost:6335/dashboard> (đổi bằng `QDRANT_HTTP_PORT` trong `.env`)

Kiểm tra catalog dev mặc định và chuẩn bị knowledge source:

```bash
docker compose exec app python -m src.cli datasets
docker compose exec app python -m src.cli prepare financial
```

Dev dùng trực tiếp SQLite nguồn ở chế độ read-only:

```bash
docker compose exec app python -m src.cli query financial "SELECT COUNT(*) AS total FROM account"
```

Bộ test cũ được chọn rõ bằng `--split test`. Database tạo từ SQL dump chỉ tồn tại trong `.runtime`:

```bash
docker compose exec app python -m src.cli datasets --split test
docker compose exec app python -m src.cli build-db financial --split test
docker compose exec app python -m src.cli query financial "SELECT COUNT(*) AS total FROM account" --split test
```

## API dữ liệu

| Endpoint | Mục đích |
|---|---|
| `GET /datasets` | Liệt kê dataset của split dev mặc định; nhận query parameter `split` |
| `POST /datasets/{name}/prepare` | Chuyển source knowledge thành Markdown |
| `POST /datasets/{name}/database` | Nạp SQL dump vào SQLite |
| `GET /datasets/{name}/schema` | Đọc schema đã nạp |
| `POST /datasets/{name}/query` | Chạy `SELECT`/`WITH`/`EXPLAIN` ở chế độ read-only |

Ví dụ build database của test split:

```json
POST /datasets/financial/database?split=test
{"overwrite": false}
```

Ví dụ query:

```json
POST /datasets/financial/query
{"sql": "SELECT COUNT(*) AS total FROM account", "limit": 200}
```

## Lựa chọn database

Kiến trúc hiện tại dùng đúng công cụ cho từng loại workload:

- **SQLite cho SQL runtime của MVP:** dev dùng trực tiếp 11 database BIRD ở chế độ read-only; test tạo SQLite tạm từ hai dump. Gold query dùng SQLite dialect (`STRFTIME`, biểu thức boolean, backtick).
- **Qdrant cho retrieval:** code đã dùng dense vector + BM25 sparse vector + hybrid rerank và named vectors; Qdrant phù hợp trực tiếp với luồng này và chạy thành service riêng trong Compose.
- **PostgreSQL cho production sau này:** nên dùng khi có ghi đồng thời, phân quyền nhiều người dùng, backup/HA và dữ liệu nghiệp vụ thật. Chỉ chuyển sau khi thêm một lớp SQL dialect và chuyển bộ benchmark khỏi các hàm riêng của SQLite. Chưa nên thêm PostgreSQL vào MVP vì sẽ tạo hai nguồn sự thật và làm sai các gold query hiện có.

## Phát triển cục bộ

```bash
uv venv --python 3.12
uv pip install --python .venv/Scripts/python.exe -e ".[dev]"
uv run python -c "import torch; print(torch.cuda.is_available(), torch.cuda.get_device_name(0))"
uv run python -m unittest discover -s tests -v
uv run python -m src.app.app
```

Trên Linux/macOS, có thể bỏ `--python .venv/Scripts/python.exe` vì `uv pip` tự tìm `.venv`. Dùng `uv lock` sau khi đổi dependency và `uv sync --frozen` trong CI/Docker để tái lập đúng môi trường.

Các dependency đọc DOCX/PDF/XLSX được tách khỏi image mặc định; cài bằng `uv pip install -e ".[documents]"` khi cần.

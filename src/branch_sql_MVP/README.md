# SQL Studio: cài mới từ GitHub và import dataset

Hướng dẫn này dùng cho người vừa clone/pull repo. **Không cần đọc lịch sử eval,
không cần BIRD, không cần `.runtime` từ máy tác giả.** App có sẵn 8 cấu hình pipeline
trong `pipeline/presets.json`. Dữ liệu do bạn import và index được tạo tại máy bạn.

## 1. Chuẩn bị

- Git và uv (trình quản lý Python). Nếu chưa có uv, cài theo https://docs.astral.sh/uv/getting-started/installation/.
- Python 3.12; uv có thể cài giúp bằng lệnh bên dưới.
- Internet ở lần cài package đầu tiên; cần tải model Hugging Face nếu tạo index.
- API key Google Gemini để chạy sinh SQL. Model mặc định: `gemini-3.5-flash-lite`.
- Chạy CPU được. NVIDIA/CUDA chỉ cần khi muốn tăng tốc embedding/reranker.
- Không cần Docker, Qdrant server, PostgreSQL hay Node.js: Studio dùng SQLite và Qdrant local.

Lưu ý dung lượng: dependency của repo có PyTorch/CUDA trên Windows/Linux, vì vậy
cài lần đầu và tạo index có thể tải nhiều GB, dù bạn chọn chạy CPU.

## 2. Clone hoặc cập nhật repo

Thay `<URL_REPO_GITHUB>` bằng URL của repository bạn đang đọc:

```powershell
git clone <URL_REPO_GITHUB> vi-coze
cd vi-coze
uv python install 3.12
uv sync --python 3.12 --extra api --extra llm --locked
```

Nếu đã có bản clone, chạy `git pull` từ thư mục repo, rồi chạy lại lệnh `uv sync`
ở trên. Giữ các chỉnh sửa cá nhân trước khi pull nếu Git báo xung đột.

Các lệnh ở phần còn lại **đều chạy từ gốc repo `vi-coze`**, nơi có `pyproject.toml`.
`--locked` kiểm tra cài đúng lockfile đã commit, không tự thay dependency.

## 3. Cấu hình API key và thiết bị

Windows PowerShell:

```powershell
Copy-Item src/branch_sql_MVP/.env.example src/branch_sql_MVP/.env
notepad src/branch_sql_MVP/.env
$env:KB_EMBEDDING_DEVICE = "cpu"
```

Linux/macOS:

```bash
cp src/branch_sql_MVP/.env.example src/branch_sql_MVP/.env
# Mở file .env bằng editor và điền khóa của bạn.
export KB_EMBEDDING_DEVICE=cpu
```

Trong file `.env`, điền:

```dotenv
GOOGLE_API_KEY=your_google_api_key
```

Chỉ copy `.env.example` **ở lần đầu**; không ghi đè `.env` đã có key.
Không commit `.env` hoặc gửi key trong issue. `.gitignore` đã loại file này.

Mọi đường dẫn tương đối trong `settings.json` được tính từ `src/branch_sql_MVP`.
Có thể sửa `embedding.device` thành `cpu` trong file đó để lưu lâu dài. Biến môi trường
`KB_EMBEDDING_DEVICE` ưu tiên hơn setting. Máy NVIDIA có thể dùng `cuda`;
kiểm tra với:

```powershell
uv run --extra api --extra llm python -c "import torch; print(torch.cuda.is_available())"
```

Studio đọc key từ `.env` ngay cạnh `settings.json`. Bạn cũng có thể nhập key tạm
trong màn hình chạy. Provider/model mặc định nằm ở `api.provider` và `api.model`.
Chọn provider và nhập model ID khác trong “Model & cấu hình chạy” để override lần chạy.

## 4. Chạy demo từ số không, không cần lịch sử eval

Tạo một SQLite giả với bảng `orders`, hai đơn hàng có tổng doanh thu 350000 VND:

```powershell
uv run --extra api --extra llm python -m src.branch_sql_MVP.examples.create_demo
uv run --extra api --extra llm python -m src.branch_sql_MVP.data.import_dataset --name shop_demo --database src/branch_sql_MVP/.runtime/demo.sqlite --business src/branch_sql_MVP/examples/business.md --question "Tổng doanh thu là bao nhiêu?"
uv run --extra api --extra llm python -m src.branch_sql_MVP.app.app
```

Mở http://127.0.0.1:8000. Chọn **P1-full**, chọn dataset **shop_demo**,
kiểm tra `google / gemini-3.5-flash-lite`, rồi bấm **Chạy thử**.

P1 đọc schema + tài liệu nghiệp vụ để sinh SQL nên **không cần embedding/index**.
SQL dự kiến có dạng `SELECT SUM(amount) FROM orders`.
Nút chạy mới gọi API model và có thể phát sinh phí theo tài khoản của bạn.
Tạo demo, import không có `--index` và mở canvas không gọi LLM.

Trang trống dataset ngay sau clone là bình thường: import theo các bước trên rồi
reload trình duyệt. Không phải tải BIRD để làm đầy trang.

**Dừng app:** nhấn `Ctrl+C` trong terminal chạy app.

## 5. Import dataset thật

Chuẩn bị hai file:

1. **SQLite `.sqlite` hoặc `.db`** chứa schema và dữ liệu; ưu tiên khai báo primary key,
   foreign key rõ ràng. Nếu dữ liệu đang ở PostgreSQL/MySQL, cần xuất/chuyển sang
   SQLite trước. Importer mới không kết nối trực tiếp vào các server đó.
2. **Tài liệu nghiệp vụ** `.md`, `.docx`, `.pdf` hoặc `.xlsx`, giải thích bảng, cột,
   đơn vị đo, quy tắc join, cách tính chỉ tiêu và các giá trị đặc biệt.
   Markdown là lựa chọn nhẹ nhất. Với XLSX, kiểm tra `preprocess.excel_sheets` trong
   Settings; đặt `[]` để đọc tất cả sheet nếu workbook không có sheet tên `dev`.

Ví dụ nội dung Markdown:

```markdown
# Bán hàng
## Dữ liệu đơn hàng
### orders
| Cột | Ý nghĩa |
| --- | --- |
| customer_id | Khóa tham chiếu customers.id |
| amount | Doanh thu, VND |
| status | paid là đã thanh toán |
Doanh thu thực thu chỉ tính đơn có status = paid.
```

Import cho P1 (không tải model embedding):

```powershell
uv run --extra api --extra llm python -m src.branch_sql_MVP.data.import_dataset --name sales_v1 --database "D:/datasets/sales.sqlite" --business "D:/datasets/business.md" --question "Tổng doanh thu thực thu là bao nhiêu?"
```

**Muốn chạy đủ 8 pipeline**, dừng app trước để Qdrant local không bị khóa, rồi import
với `--index`. Ví dụ tạo một phiên bản khác:

```powershell
uv run --extra api --extra llm python -m src.branch_sql_MVP.data.import_dataset --name sales_v2 --database "D:/datasets/sales.sqlite" --business "D:/datasets/business.md" --question "Tổng doanh thu thực thu là bao nhiêu?" --index
```

Tên dataset: chữ thường, số và `_`, bắt đầu bằng chữ, tối đa 64 ký tự.
Importer từ chối tên đã tồn tại để tránh ghi đè dữ liệu; dùng tên phiên bản mới nếu
muốn cập nhật dữ liệu hoặc thêm index cho một bản import P1 trước đó.

Không cần file gold SQL, câu trả lời đúng hoặc tập eval. Câu hỏi ở `--question` chỉ
là câu hỏi mở đầu; bạn sửa được ngay trong UI.

Với PDF, cài thêm bộ parse trước khi import:

```powershell
uv sync --extra api --extra llm --extra pdf --locked
```

Sau đó dùng cùng lệnh import nhưng thêm `--extra pdf` ngay sau `uv run`.
Model phân tích PDF có thể được tải thêm ở lần đầu. DOCX/XLSX đã có dependency
trong bộ cài cơ bản của repository.

## 6. Importer tạo những gì?

Mỗi dataset được lưu tại `src/branch_sql_MVP/.runtime/studio/datasets/<name>/`:

- `database.sqlite`: bản sao SQLite, không sửa file nguồn.
- `business.md`: tài liệu chuẩn hóa.
- `schema.json`: schema catalog và sample values.
- `events.json`: event–entity index.
- `dataset.json`: thông tin đăng ký, câu hỏi mở đầu và trạng thái `indexed`.

Khi có `--index`, importer chạy thêm extract → link → chunk → embed → Qdrant.
Các collection có tiền tố `studio_<name>`, nằm tại `.runtime/studio/qdrant`.
Việc tạo index này không cần gọi LLM; có thể tải embedding/reranker từ Hugging Face.
Metadata/manifest được ghi sau khi import thành công. Nếu import lỗi giữa chừng,
folder chưa hoàn tất được giữ để kiểm tra; chạy lại với tên mới sau khi sửa nguyên nhân.

Các pipeline B4/B5/B6/G1 yêu cầu `indexed=true`; app trả thông báo rõ nếu bạn chọn
chúng trên dataset chỉ import cho P1. Graph/community của công cụ nâng cao là tính
năng riêng; không cần bật để tạo event index và chạy các pipeline này.

## 7. Khởi động lại và sử dụng

```powershell
uv run --extra api --extra llm python -m src.branch_sql_MVP.app.app
```

- `/`: Studio, chọn pipeline → dataset → câu hỏi → LLM → Chạy thử.
- `/ui`: công cụ tài liệu, offline, graph và toàn bộ settings nâng cao.
- `/docs`: tài liệu API FastAPI.
- `/health`: kiểm tra server sống.

Nhấn node để xem output; trace cập nhật khi chạy. Settings chung không sửa các bản
benchmark lịch sử. Chức năng “Xem lần chạy đã lưu” chỉ khả dụng khi máy có archive
benchmark cũ; **không phải bước trong quy trình setup hoặc import mới**.

## 8. Lỗi thường gặp

| Hiện tượng | Cách xử lý |
| --- | --- |
| Không thấy dataset | Import thành công rồi reload trang; kiểm tra đã có `dataset.json`. |
| Thiếu API key | Điền `GOOGLE_API_KEY` trong đúng `src/branch_sql_MVP/.env`. |
| Model 404 hoặc quyền truy cập | Kiểm tra model ID và quyền model của key; chọn model khác trong UI. |
| CUDA unavailable / out of memory | Dùng `KB_EMBEDDING_DEVICE=cpu`, giảm batch size trong Settings. |
| Qdrant storage already accessed | Dừng app bằng Ctrl+C trước khi import; chỉ chạy một app dùng cùng Qdrant local. |
| Dataset chưa có vector index | Import phiên bản mới với `--index`, rồi chọn phiên bản đó. |
| FileExistsError khi import | Dataset name đã tồn tại; dùng tên mới, không ghi đè. |
| Cổng 8000 đang được sử dụng | Dừng server cũ; hoặc chạy `uv run --extra api --extra llm uvicorn src.branch_sql_MVP.app.app:app --host 127.0.0.1 --port 8001`. |
| Download package/model thất bại | Kiểm tra mạng/proxy, dung lượng ổ đĩa; chạy lại bước cài/import. |

## 9. Kiểm tra clone mới

Test dưới đây tạo dataset giả trong thư mục tạm, giả lập model và không đọc bundle eval:

```powershell
uv run --extra api --extra llm python -m pytest src/branch_sql_MVP/tests/test_fresh_setup.py -q
```

Test kiểm tra app mở được 8 pipeline khi chưa có dữ liệu, import dataset mới, sinh SQL
qua workflow thật với model giả, chặn ghi đè và thông báo thiếu index.
Không dùng toàn bộ test benchmark làm tiêu chí cài mới vì một số test đó cần dataset
BIRD riêng không phân phối trong Git.

## 10. Những file cần có trên GitHub

Cần commit code nhánh MVP, `pipeline/presets.json`, `examples/`, `.env.example`,
README này, `pyproject.toml`, `uv.lock` và test fresh setup cùng nhau.
Không commit `.env`, `.runtime`, dữ liệu riêng hoặc cache model. Người clone tự
cài dependency, nhập key và import dữ liệu; không sao chép đường dẫn máy tác giả.

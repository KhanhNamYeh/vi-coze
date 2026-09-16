# SQL Studio: cài mới từ GitHub và import dataset

Tài liệu phát triển: [Hướng dẫn agent triển khai node dùng chung và UI offline/online](../../docs/AGENT_WORKFLOW_IMPLEMENTATION.md). Tiêu chí nghiệm thu và phần còn thiếu được ghi riêng trong [báo cáo kiểm tra](../../docs/WORKFLOW_MILESTONE_STATUS.md); hướng dẫn bên dưới dùng editor hiện tại.

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

Studio đọc key từ `.env` ngay cạnh `settings.json`. Provider/model mặc định nằm ở
`api.provider` và `api.model` trong **Settings → api**. Mỗi node **LLM** có ô
Provider/Model riêng; để trống để kế thừa. API chạy cũng hỗ trợ key tạm trong bộ nhớ,
nhưng editor hiện dùng key môi trường, không có ô lưu API key.

## Phân biệt file ví dụ và dữ liệu của bạn

**`D:/datasets/sales.sqlite` và `D:/datasets/business.md` được nhắc trong hướng dẫn
chỉ là đường dẫn minh họa. Repo không có sẵn hai file tại các đường dẫn đó.**
Bạn phải thay chúng bằng đường dẫn tới file thật trên máy; không cần đặt tên file
đúng là `sales.sqlite` hoặc `business.md`.

| File / thư mục | Có sẵn khi clone? | Cách sử dụng |
| --- | --- | --- |
| `examples/business.md` trong nhánh MVP | Có | Tài liệu cho database demo `orders`, không phải tài liệu chung cho mọi database. |
| `.runtime/demo.sqlite` trong nhánh MVP | Chưa có | Tạo bằng lệnh `examples.create_demo` ở mục 4. |
| `D:/datasets/sales.sqlite` | Không, chỉ là ví dụ | Thay bằng SQLite chứa dữ liệu thật của bạn. |
| `D:/datasets/business.md` | Không, chỉ là ví dụ | Tự viết hoặc cung cấp tài liệu mô tả đúng database của bạn. |
| `data/dev`, `data/test` trong nhánh MVP | Không phân phối trong Git | Dataset cũ ở máy tác giả; không cần cho quy trình import mới. |

**Không cần chép dữ liệu mới vào `data/`.** Lệnh import nhận đường dẫn file bất kỳ
trên máy, tự sao chép và đăng ký dataset. Chỉ thả file vào `data/` sẽ không tự đăng
ký dataset mới trong Studio. Bạn cũng không cần lấy một bộ dữ liệu cũ để thay cho
hai file minh họa.

## 4. Chạy demo từ số không, không cần lịch sử eval

Tạo một SQLite giả với bảng `orders`, hai đơn hàng có tổng doanh thu 350000 VND:

```powershell
uv run --extra api --extra llm python -m src.branch_sql_MVP.examples.create_demo
uv run --extra api --extra llm python -m src.branch_sql_MVP.data.import_dataset --name shop_demo --database src/branch_sql_MVP/.runtime/demo.sqlite --business src/branch_sql_MVP/examples/business.md --question "Tổng doanh thu là bao nhiêu?"
uv run --extra api --extra llm python -m src.branch_sql_MVP.app.app
```

Mở http://127.0.0.1:8000. Chọn thẻ **Prompt cơ bản** (`P1-full`), chọn dataset
**shop_demo**, chọn chế độ **SQL, dữ liệu & câu trả lời**, rồi bấm
**Chạy toàn pipeline**. App tự lưu cấu hình dưới id của pipeline trước khi chạy;
kết quả gồm SQL, bảng dữ liệu và câu trả lời ở ba tab dưới sơ đồ.

P1 đọc schema + tài liệu nghiệp vụ để sinh SQL nên **không cần embedding/index**.
SQL dự kiến có dạng `SELECT SUM(amount) FROM orders`.
Nút chạy mới gọi API model và có thể phát sinh phí theo tài khoản của bạn.
Tạo demo, import không có `--index` và mở canvas không gọi LLM.

Trang trống dataset ngay sau clone là bình thường: import theo các bước trên rồi
reload trình duyệt. Không phải tải BIRD để làm đầy trang.

**Dừng app:** nhấn `Ctrl+C` trong terminal chạy app.

## 5. Import dataset thật

### 5.1. Chuẩn bị database và tài liệu tương ứng

Ví dụ bạn có thư mục ngoài repo như sau (bạn tự cung cấp các file này):

```text
D:/du_lieu_cong_ty/
├── ban_hang.sqlite
└── mo_ta_nghiep_vu.md
```

Chuẩn bị hai file:

1. **SQLite `.sqlite` hoặc `.db`** chứa schema và dữ liệu; ưu tiên khai báo primary key,
   foreign key rõ ràng. Nếu dữ liệu đang ở PostgreSQL/MySQL, cần xuất/chuyển sang
   SQLite trước. CSV/Excel chứa các dòng dữ liệu cũng cần được nạp thành bảng trong
   SQLite; **đổi đuôi `.csv`/`.xlsx` thành `.sqlite` không chuyển được định dạng**.
   Importer mới không kết nối trực tiếp vào các server đó.
2. **Tài liệu nghiệp vụ** `.md`, `.docx`, `.pdf` hoặc `.xlsx`, giải thích bảng, cột,
   đơn vị đo, quy tắc join, cách tính chỉ tiêu và các giá trị đặc biệt.
   Markdown là lựa chọn nhẹ nhất. Với XLSX, kiểm tra `preprocess.excel_sheets` trong
   Settings; đặt `[]` để đọc tất cả sheet nếu workbook không có sheet tên `dev`.

File đưa vào `--database` là database để truy vấn; file đưa vào `--business` là
ngữ cảnh giúp model hiểu database. Một file Excel ở `--business` được đọc như tài
liệu, không tự tạo bảng SQLite.

Có thể dùng editor bất kỳ để tạo file `.md`, lưu UTF-8. Mô tả tên bảng/cột **đúng
như trong SQLite**, quan hệ khóa ngoại, đơn vị tiền/ngày và quy tắc tính toán.
Không dùng nguyên tài liệu demo nếu schema của bạn khác bảng `orders`.

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

### 5.2. Kiểm tra file và dừng app trước khi import

Nếu app đang chạy, nhấn `Ctrl+C` tại terminal chạy app. Từ gốc `vi-coze`, kiểm tra
hai đường dẫn thật bằng PowerShell (cả hai phải trả về `True`):

```powershell
Test-Path "D:/du_lieu_cong_ty/ban_hang.sqlite"
Test-Path "D:/du_lieu_cong_ty/mo_ta_nghiep_vu.md"
```

Có thể dùng đường dẫn tuyệt đối như trên hoặc đường dẫn tương đối tính từ thư mục
terminal đang đứng. Luôn đặt đường dẫn có khoảng trắng trong dấu ngoặc kép.

### 5.3. Chọn một cách import

**Cách A — chỉ chạy P1**, không tải model embedding:

```powershell
uv run --extra api --extra llm python -m src.branch_sql_MVP.data.import_dataset --name sales_v1 --database "D:/du_lieu_cong_ty/ban_hang.sqlite" --business "D:/du_lieu_cong_ty/mo_ta_nghiep_vu.md" --question "Tổng doanh thu thực thu là bao nhiêu?"
```

**Cách B — chạy đủ 8 pipeline**, thêm `--index`. Dùng tên khác nếu đã chạy cách A;
không bắt buộc chạy cách A trước cách B:

```powershell
uv run --extra api --extra llm python -m src.branch_sql_MVP.data.import_dataset --name sales_v2 --database "D:/du_lieu_cong_ty/ban_hang.sqlite" --business "D:/du_lieu_cong_ty/mo_ta_nghiep_vu.md" --question "Tổng doanh thu thực thu là bao nhiêu?" --index
```

Ý nghĩa các tham số:

| Tham số | Nội dung cần điền |
| --- | --- |
| `--name` | Tên đăng ký hiển thị trong app, ví dụ `sales_v1`; không phải tên file. |
| `--database` | Đường dẫn tới SQLite thật của bạn. |
| `--business` | Đường dẫn tới tài liệu mô tả database đó. |
| `--question` | Câu hỏi mở đầu, sửa được trong UI; không phải câu trả lời hay gold SQL. |
| `--index` | Thêm bước tạo embedding + Qdrant để chạy các pipeline truy hồi. |

Tên dataset: chữ thường, số và `_`, bắt đầu bằng chữ, tối đa 64 ký tự.
Importer từ chối tên đã tồn tại để tránh ghi đè dữ liệu; dùng tên phiên bản mới nếu
muốn cập nhật dữ liệu hoặc thêm index cho một bản import P1 trước đó.

Không cần file gold SQL, câu trả lời đúng hoặc tập eval. Câu hỏi ở `--question` chỉ
là câu hỏi mở đầu; bạn sửa được ngay trong UI.

### 5.4. Kiểm tra import thành công và chạy trên UI

Lệnh thành công in JSON có `id` bằng tên dataset, `knowledge_id`, `doc_id` và
`indexed`. Cách A có `indexed: false`; cách B hoàn tất có `indexed: true`.
Nếu terminal có traceback/lỗi thì chưa coi là import hoàn tất.

Khởi động app:

```powershell
uv run --extra api --extra llm python -m src.branch_sql_MVP.app.app
```

Mở http://127.0.0.1:8000, rồi:

1. Chọn thẻ **Prompt cơ bản** (`P1-full`) nếu import cách A; cách B cho phép chọn
   cả 8 pipeline.
2. Trong dropdown **Dữ liệu** trên thanh công cụ, chọn `sales_v1` hoặc `sales_v2`.
3. Nhập câu hỏi về dữ liệu của bạn ở panel bên phải.
4. Chọn node **Generate** để xem prompt và model hiệu lực; API key lấy từ `.env`.
   Bấm **✕ Về câu hỏi** để quay lại ô nhập câu hỏi.
5. Chọn chế độ **SQL, dữ liệu & câu trả lời**, bấm **Chạy toàn pipeline**. Xem
   câu trả lời, SQL và bảng dữ liệu ở ba tab ngay dưới sơ đồ, nhật ký thật nằm
   trong mục **Nhật ký**. **SQL only** giữ chế độ phục vụ benchmark.

Nếu đã mở trang trước khi import thì reload trang. Sau này dữ liệu thay đổi, import
lại với tên phiên bản mới; sửa file nguồn không tự cập nhật bản sao/index trong app.

### 5.5. Nếu tài liệu nghiệp vụ là PDF

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
Manifest ready được ghi sau khi import thành công. `offline-status.json` giữ lỗi
kể cả trước khi có manifest. Với workflow offline đã lưu trên UI, sửa nguyên nhân
rồi chạy lại cùng workflow để resume; cache kiểm tra fingerprint và checksum. CLI
import vẫn từ chối tên đã tồn tại: dùng tên mới khi chạy lại bằng CLI.

Các pipeline B4/B5/B6/G1 yêu cầu `indexed=true`; app trả thông báo rõ nếu bạn chọn
chúng trên dataset chỉ import cho P1. Graph/community của công cụ nâng cao là tính
năng riêng; không cần bật để tạo event index và chạy các pipeline này.

## 7. Khởi động lại và sử dụng

```powershell
uv run --extra api --extra llm python -m src.branch_sql_MVP.app.app
```

- `/`: Studio, chọn thẻ pipeline → dataset + model → câu hỏi → **Chạy toàn pipeline**.
- Settings cơ bản và toàn bộ JSON nâng cao đều ở trang **Settings** của Studio. `/ui` chỉ còn là giao diện tương thích cho các công cụ cũ, không cần trong luồng import/chạy pipeline.
- `/docs`: tài liệu API FastAPI.
- `/health`: kiểm tra server sống.

Nhấn node và chọn invocation để xem output từng lần. **Lịch sử chạy** đọc run mới
được lưu bền vững bằng SQLite, không cần archive benchmark. Khi restart, run chưa
xong được đánh dấu interrupted khi dịch vụ job khởi tạo; app không tự gọi lại LLM.

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


## 11. Làm toàn bộ từ editor offline/online

1. Tạo database demo bằng lệnh `examples.create_demo` ở mục 4, rồi chạy app.
   Không cần chạy lệnh importer nếu muốn dùng form upload.
2. Mở **Dữ liệu & Offline**. Nhập tên mới, chọn file
   `src/branch_sql_MVP/.runtime/demo.sqlite` và
   `src/branch_sql_MVP/examples/business.md` bằng nút chọn file.
3. Lần đầu để **Tạo index truy hồi** và **GraphRAG** tắt. Bấm **Import**:
   thao tác này chỉ upload và mở workflow, chưa công bố dataset ready.
4. Trong editor offline, chọn từng node để xem config/input, rồi bấm
   **Chạy toàn pipeline**. Cấu hình được lưu tự động khi chạy. Các bước
   validate, preprocess, schema, event, register chạy thật.
5. Sau trạng thái completed, mở **Dữ liệu & Offline**, chọn thẻ dataset, mở
   **P1-full**, nhập câu hỏi và chọn chế độ answer. P1 không cần index.
6. Để dùng B4/B5/B6/G1, upload cùng nguồn với tên phiên bản mới và bật index.
   Chỉ khi bước index và register thành công, dataset mới có capability index.
   GraphRAG là tùy chọn riêng có gọi LLM; event index không gọi LLM.
7. Lịch sử và event có sequence sống qua reload. Nút dừng yêu cầu hủy tại ranh
   giới node, không hứa ngắt tức thì API/GPU call đang chạy.

### Chạy demo và debug pipeline có sẵn

UI sử dụng tám pipeline có sẵn; không cần tạo node, nối cạnh hoặc dựng workflow.

1. Trang đầu hiển thị tám thẻ pipeline kèm tên, mô tả ngắn và nhãn cho biết
   pipeline đó có cần index hay không. Bấm một thẻ để mở toàn bộ sơ đồ.
2. Thanh trên chọn pipeline, dataset, Provider và Model, rồi bấm
   **Chạy toàn pipeline**. Provider và Model là hai ô riêng; đổi ô nào cũng ghi
   thẳng vào Settings của workspace.
3. Panel bên phải mặc định là ô nhập câu hỏi. Bấm một node trên sơ đồ để chuyển
   sang **Cấu hình · Input · Output** của node đó; bấm **✕ Về câu hỏi** để quay lại.
4. Node LLM có System/User prompt, Provider, Model, Temperature và Max tokens ở
   dạng ô nhập riêng; để trống provider/model để kế thừa workspace. JSON thô nằm
   trong mục **Nâng cao**, không chiếm màn hình mặc định.
5. Cấu hình được lưu tự động dưới chính id của pipeline mẫu khi bạn chạy hoặc
   debug; template gốc trên đĩa không bị sửa. Khi đang dùng bản đã tùy chỉnh,
   thanh trên hiện nhãn **Đã tùy chỉnh** và nút **Khôi phục mặc định**.
6. Kết quả nằm dưới sơ đồ với ba tab **Câu trả lời · SQL · Bảng dữ liệu**, kèm
   **Nhật ký** thu gọn được. Node lỗi được tô đỏ và gắn dấu `!` trên sơ đồ.
7. Chọn node → **Output**, chọn invocation để xem input/output hoặc lỗi. Loop có
   nhiều invocation riêng; danh sách chỉ hiện invocation đúng luồng đang xem.
8. Nút **Lấy input từ lần chạy trước** điền input thật của invocation đã chọn;
   hoặc tự nhập JSON trong mục **Nâng cao**. **Preview prompt** chỉ xem prompt.
   **Chạy node** chạy đúng node được chọn, không tự chạy upstream. Nếu có run đã
   chọn, debug dùng snapshot settings và output của run đó. LLM debug có thể phát
   sinh phí; offline debug có thể ghi artifact và vẫn tuân theo bảo vệ dataset ready.
9. Với loop/fan-out, node có dấu `⧉`; bấm **Mở luồng con** để chọn node bên trong
   và debug. Không debug lại cả composite nếu chỉ muốn kiểm tra một LLM con.

### Dữ liệu và cache khi resume

Workflow của người dùng nằm trong `.runtime/studio/workflows`; lịch sử job trong
`.runtime/studio/runs/runs.sqlite`. Dataset chứa thêm `cache/`, `markdown/` và
`artifacts/`, tách riêng theo tên. Không chép những thư mục này lên GitHub.

Resume kiểm tra nguồn, config liên quan và checksum của artifact từng stage.
Thay chunk làm downstream stale; đổi prompt trả lời không làm index stale.
Không sửa nguồn trong một tên dataset đang import: tạo tên phiên bản mới nếu SQLite
hoặc tài liệu thay đổi. Dataset đã ready không được ghi đè qua offline workflow.
Chỉ chạy một tiến trình app dùng cùng Qdrant local; job cùng dataset bị từ chối
khi một job khác đang queued/running.

GraphRAG đã có các LLM node hiển thị, nhưng cache/resume từng LLM extraction/report
và kiểm thử tích hợp GraphRAG vẫn chưa được nghiệm thu đầy đủ. Xem báo cáo mốc trước
khi dùng khả năng này làm tiêu chí hoàn thành M4.


### Tài liệu mới có cấu trúc khác bộ cũ

Preset chunk giữ `heading_level=2`, `child_min=40`, đơn vị token. Với Markdown,
đặt nội dung dưới heading `## ...`, hoặc sửa riêng node **Chunk**:

```json
{"settings":{"chunk":{"heading_level":1,"child_min":1}}}
```

Ví dụ trên phù hợp demo chỉ có H1 và vài dòng. Với tài liệu thực, chọn ngưỡng theo
độ dài nội dung của bạn; không cần đổi setting toàn workspace. Lỗi “yêu cầu H2”
hoặc “0 child chunk” nghĩa là cấu trúc/ngưỡng chunk chưa phù hợp, chưa phải lỗi LLM.
Index dùng collection theo fingerprint: thay cấu hình tạo collection mới và chỉ
công bố tên collection trong manifest khi kiểm tra thành công. Collection cũ không
bị xóa hoặc tạo lại trong quá trình resume.


### Thao tác MVP nhanh

1. Mở **Settings → Cấu hình cơ bản**: chọn provider, nhập model ID và chọn CPU/CUDA.
   Bấm **Lưu cấu hình cơ bản**. Provider và Model cũng đổi được ngay trên thanh
   công cụ của màn hình pipeline. Các setting khác nằm trong nhóm JSON nâng cao.
2. Mở **Dữ liệu & Offline**. Với dữ liệu của bạn: upload SQLite và tài liệu, rồi
   bấm **Chạy toàn pipeline** trong workflow được mở. Với dữ liệu có sẵn trong
   repo: bấm **Schema only** (đủ cho P1) hoặc **Có index** (cho B4/B5/B6/G1).
   Khi completed, chọn dataset ở nhóm **Dữ liệu đã import**.
3. Mở thẻ **Prompt cơ bản**, chọn dataset, nhập câu hỏi. Muốn sửa prompt/model
   riêng, chọn node **Generate → Cấu hình**. Chọn chế độ
   **SQL, dữ liệu & câu trả lời** rồi bấm **Chạy toàn pipeline**; app tự lưu
   cấu hình trước khi chạy.
4. Xem câu trả lời, SQL và bảng kết quả ở ba tab dưới sơ đồ. **Lịch sử chạy**
   mở lại run khi chuyển pipeline hoặc reload. Đổi pipeline không hủy job cũ và
   không trộn kết quả job cũ vào pipeline mới.
5. Dừng terminal bằng Ctrl+C khi dùng xong. Không cần mở giao diện `/ui`.


### Chọn pipeline trước, chạy trong màn hình sơ đồ

Mở `http://127.0.0.1:8000/`, chọn một thẻ pipeline. Màn hình tiếp theo hiển thị
đầy đủ sơ đồ và thanh **Chọn dữ liệu → Câu hỏi → Chạy toàn pipeline**.
Chọn node để sửa cấu hình/prompt, debug và xem input/output. Trang đầu không có
form chạy nhanh. Nếu chưa có dataset, import trong **Dữ liệu & Offline** trước.

# Báo cáo kỹ thuật — Pipeline offline nhánh SQL

## 1. Tổng quan

Nhánh `src/branch_sql` xử lý tài liệu tri thức thành chunk có thể truy hồi, qua sáu chặng tất định:

```
parse -> extract -> link -> chunk -> embed -> index
```

Chặng thứ bảy, `verify`, đứng ngoài chuỗi và trả lời câu hỏi "index đã dùng được chưa".

Sản phẩm định vị là **platform**. Đơn vị khai báo là **bộ tri thức** (`knowledge`): một nguồn, một cách xử lý, thuộc một hoặc nhiều **dự án**. Mỗi dự án là một hộp đen — artifact và collection tách hẳn, không có đường nào để dự án này nhìn thấy dữ liệu của dự án kia.

```jsonc
"knowledge": [
  { "id": "schema_docx", "source": "Mô tả bảng BĐS (NEW).docx",
    "project": 1,      "collection": "sqlp{project}__docs", "chunk": { ... } },
  { "id": "schema_pdf",  "source": "Mô tả bảng BĐS (NEW).pdf",
    "project": 2,      "collection": "sqlp{project}__docs", "chunk": { ... } },
  { "id": "sql_sample",  "source": "Text2SQL_testcase.xlsx",
    "project": [1, 2], "collection": "sqlp{project}__sql",  "chunk": { ... } }
]
```

Khai chung một bộ tri thức cho nhiều dự án nghĩa là **khai một lần rồi vật chất hoá thành nhiều bản**, không phải trỏ chung vào một kho. Nếu một bộ tri thức thuộc nhiều dự án mà tên collection cố định, profile không nạp được.

| | Dự án 1 | Dự án 2 |
|---|---|---|
| Tài liệu schema | `.docx` → `sqlp1__docs` | `.pdf` → `sqlp2__docs` |
| SQL sample | `.xlsx` → `sqlp1__sql` | `.xlsx` → `sqlp2__sql` |
| Artifact | `data/processed/sql/p1/` | `data/processed/sql/p2/` |

Lệnh chạy:

```bash
VI_COZE_PROJECT=1 uv run python -m src.branch_sql.offline 1 --recreate
VI_COZE_PROJECT=2 uv run --extra pdf python -m src.branch_sql.offline 2 --recreate
```

---

## 2. `parse/` — Tài liệu gốc thành Markdown

### 2.1. Đầu vào

Các định dạng được hỗ trợ: `.docx`, `.pdf`, `.xlsx`.

Danh sách định dạng được khai báo tại `parse.suffixes` trong `config/sql.json`.

Thư mục đầu vào mặc định: `data/raw/sql/` — dùng chung cho mọi dự án.

### 2.2. Nhiệm vụ

#### 2.2.1. Đặt định danh tài liệu

Parser tạo `doc_id` bằng cách: chuyển tên tài liệu thành slug; loại bỏ dấu tiếng Việt; chuẩn hóa ký tự đặc biệt; gắn thêm đuôi định dạng nguồn.

Ví dụ: `Mô tả bảng BĐS (NEW).docx` được chuyển thành `mo_ta_bang_bds_new__docx`.

Đuôi nguồn được giữ trong `doc_id` để bản DOCX và PDF của cùng tài liệu không ghi đè artifact của nhau.

Trước khi xử lý file, parser quét thư mục nguồn. Nếu hai file khác nhau tạo ra cùng một `doc_id`, pipeline dừng và báo đầy đủ tên của hai file xung đột.

#### 2.2.2. Nhận diện định dạng và chọn loader

Định dạng được nhận diện theo phần mở rộng file và đối chiếu với `parse.suffixes`. Nếu phần mở rộng không được khai báo, pipeline từ chối file và trả về thông báo chứa danh sách các định dạng được hỗ trợ.

Loader được lựa chọn như sau:

- `.pdf` → `pdf_parse` → Docling
- `.xlsx` → `xlsx_parse` → openpyxl
- `.docx` và còn lại → `docx_parse` → MarkItDown/Mammoth

Docling có chi phí khởi tạo lớn nên chỉ được import khi pipeline thực sự gặp tài liệu PDF.

#### 2.2.3. Mở và giải mã file

Đối với DOCX, MarkItDown gọi Mammoth để đọc cấu trúc OOXML và trả về Markdown thô.

Đối với PDF, Docling chạy mô hình nhận diện layout với `do_table_structure=True`. Kết quả là một `DoclingDocument`, tức cây object gồm các item, marker, text và table, không phải Markdown hoàn chỉnh. Pipeline đọc trực tiếp object model này để khôi phục cấu trúc trước khi tuần tự hóa thành Markdown.

Đối với XLSX, openpyxl đọc sheet ở chế độ read-only. Sheet nào ứng với vai trò nào được khai tại `parse.sheets`.

#### 2.2.4. Khôi phục cấp bậc tiêu đề

Ba định dạng sử dụng ba bộ luật khác nhau do lỗi cấu trúc của chúng không giống nhau.

**DOCX.** Trong tài liệu nguồn, tên bảng có thể sử dụng style `normal`. MarkItDown vì vậy xuất tên bảng thành bullet in đậm:

```
* 1. **Bảng X**
```

Hàm `docx_parse.restructure()` chuyển dòng này thành heading cấp hai:

```
## Bảng X
```

Mẫu nhận diện được khai báo tại `parse.table_heading`. Mẫu phải khớp: bullet đầu dòng; số thứ tự; toàn bộ tên bảng được in đậm. Nhóm bắt `name` được dùng trực tiếp làm nội dung heading.

Nội dung đứng trước heading cấp một đầu tiên được coi là bìa hoặc mục lục và bị loại. Các link neo sinh từ mục lục cũng được loại bỏ. Ký tự bullet ở đầu mọi dòng danh sách bị cắt trên toàn tài liệu.

Đây là quy tắc đặc thù của profile SQL. Nếu áp dụng cho loại tài liệu khác, cần kiểm tra để tránh loại nhầm phần mở đầu có nội dung thực hoặc làm mất cấu trúc danh sách. Cấp heading xuất ra hiện đặt cứng là hai, không đọc từ profile.

**PDF.** Pipeline đọc trực tiếp object model của Docling và không gọi `export_to_markdown()` cho toàn bộ tài liệu.

Docling có thể: gán mọi tiêu đề thành `level=1`; nhận diện sai tên bảng thành list item; vẫn giữ số thứ tự trong `text` hoặc `item.marker`.

Vì vậy, số thứ tự được dùng để xác định cấp heading:

- `1.` → heading cấp một, role `section`
- `1.1.` → heading cấp hai, role `table`

Quy tắc này được áp dụng cho mọi item, không phụ thuộc hoàn toàn vào nhãn do Docling sinh ra. Chỉ nhận marker từ hai cấp trở lên, vì gạch đầu dòng trong thân bài cũng được đánh số nhưng luôn một cấp.

Nội dung đứng trước tiêu đề đánh số đầu tiên được coi là bìa hoặc mục lục và bị loại. Tài liệu PDF không đánh số tiêu đề sẽ cho ra Markdown rỗng.

**XLSX.** Mỗi hàng Excel thành một mục có tiêu đề là mã testcase, bên dưới là ba nhãn `query:`, `evidence:`, `sql:`. Câu SQL nằm trong khối fence chứ không thả trần: SQL vốn thụt đầu dòng bằng khoảng trắng, để trần thì CommonMark nuốt thành indented code block và ranh giới đoạn lệch đi.

Chỉ sheet vai trò `dev` được dựng thành Markdown để đem đi index. Sheet `test` là bộ giữ kín, chỉ sinh JSON qua `eval/gold_parse.py`.

#### 2.2.5. Nối bảng PDF bị ngắt trang

Docling có thể tách một bảng thành nhiều table item theo ranh giới trang. Phần tiếp theo của bảng thường không có dòng tiêu đề thực.

Việc nối bảng được thực hiện trong `parse/` vì cần xảy ra trước khi tạo canonical Markdown. Nếu để đến `extract/`, hàng dữ liệu đầu tiên của phần tiếp theo có thể bị hiểu nhầm thành tên cột.

Điều kiện nối hiện tại chỉ có một: hai table item liền nhau trong reading order, tức không có bất kỳ item nào khác nằm giữa. Một đoạn văn hay một heading xen vào là đủ để pipeline giữ chúng tách rời.

Pipeline **không** kiểm tra ranh giới trang, **không** so số cột, **không** xác minh table item thứ hai có header hợp lệ hay không, và **không** sinh cảnh báo cho thao tác nối. Đây là luật yếu nhất trong chặng này.

#### 2.2.6. Làm sạch văn bản

Cả ba định dạng sử dụng chung hàm `sanitize()`. Các thao tác bao gồm: chuẩn hóa Unicode NFC; loại ký tự vô hình; loại HTML comment; loại các thẻ HTML theo danh sách trắng tên thẻ, nên placeholder dạng `<NEW>`, `<ten_user>` được giữ lại; cảnh báo chính xác các loại thẻ đã bị loại; bỏ dải gạch ngang dùng để ngăn mục; sửa lỗi gõ theo `parse.replacements`; phát hiện dòng có dấu hiệu prompt injection và sinh cảnh báo nhưng không xóa nội dung; bỏ khoảng trắng cuối dòng; co khoảng trắng thừa; giới hạn số dòng trống liên tiếp.

Markdown có độ dài dưới 50 ký tự bị từ chối để tránh chuyển tài liệu rỗng hoặc PDF scan chưa OCR sang bước tiếp theo. Ngưỡng này là kiểm tra kỹ thuật tối thiểu, không phải đánh giá đầy đủ chất lượng nội dung.

#### 2.2.7. Giữ metadata tối thiểu

Parse giữ các metadata sau trong bộ nhớ: `doc_id`, `title`, `source_name`, `warnings[]`. Metadata được truyền trực tiếp sang `extract/`. Parse không tạo file metadata riêng.

### 2.3. Thư viện

- `markitdown[docx]`: chuyển DOCX thành Markdown.
- `docling`: đọc PDF thành object model và nhận diện cấu trúc bảng.
- `openpyxl`: đọc sheet của XLSX.
- `langchain-core`: biểu diễn Document và metadata trong bộ nhớ.
- `pydantic`: đọc và kiểm tra profile cấu hình.

### 2.4. Đầu ra

Artifact duy nhất của parse: `data/processed/sql/p<project>/<doc_id>.md`

Parse không tạo: DocumentIR; `blocks[]`; file metadata sidecar.

### 2.5. Kết quả

| Chỉ số | DOCX | PDF | XLSX |
|---|---|---|---|
| Heading section | 7 | 7 | 1 |
| Heading cấp hai | 18 | 18 | 18 |
| Bảng | 18 | 18 | 0 |
| Tổng hàng dữ liệu | 194 | 194 | — |
| Độ dài Markdown | — | — | 18.353 ký tự |
| Thời gian convert quan sát | Dưới 1 giây | Khoảng 75 giây | Dưới 1 giây |

### 2.6. Giới hạn hiện tại

- Không giữ bounding box.
- Không giữ số trang trong artifact Markdown.
- Không giữ ảnh, figure, caption, header/footer hoặc tài sản gốc. Với PDF, đây là mất mát so với object model ban đầu của Docling.
- Định dạng được nhận diện theo phần mở rộng file, chưa kiểm tra magic bytes.
- Luật nối bảng PDF chỉ dựa vào tính liền kề và không sinh cảnh báo.
- Nhánh DOCX bỏ mọi nội dung trước heading cấp một đầu tiên và cắt ký tự bullet trên toàn tài liệu.
- Nhánh PDF phụ thuộc việc tài liệu có đánh số tiêu đề.
- Tên file không dùng chữ Latin cho ra `doc_id` rỗng.
- Nếu có cả DOCX và PDF tương đương, nên ưu tiên DOCX vì nhanh hơn và không cần mô hình layout.
- Khi chỉ chạy riêng `parse/`, artifact `.md` không chứa đầy đủ warning.

---

## 3. `extract/` — Markdown thành structured elements độc lập

### 3.1. Đầu vào

Extract nhận file `<doc_id>.md` do `parse/` tạo, nằm tại `data/processed/sql/p<project>/`.

### 3.2. Nhiệm vụ

#### 3.2.1. `blocks.py` — tách block

Module sử dụng `markdown-it-py` với CommonMark và hỗ trợ bảng GFM để nhận diện các block cấp ngoài cùng: heading; paragraph; list; table; quote; code; HTML.

Extract không sử dụng regex để tách cấu trúc Markdown. Nhờ đó, parser xử lý đúng: code fence; heading dạng gạch dưới; danh sách lồng; dấu `|` được escape trong ô bảng.

Khoảng dòng được lấy từ `token.map` và chuyển sang chỉ số 1-based: `line_start`, `line_end`.

Block được đánh ID theo thứ tự đọc: `block_1`, `block_2`, ... Thứ tự đọc là thứ tự phần tử trong mảng.

Vai trò heading được lấy từ `extract.heading_roles`: `#` → section, `##` → table. Extract không phụ thuộc vào `chunk.split_on`.

Cảnh báo cấu trúc được sinh khi: tài liệu không có block, thiếu heading role yêu cầu, hoặc heading level không nằm trong `extract.heading_roles`.

#### 3.2.2. `block_extract.py` — đọc nội dung block

Bộ xử lý được chọn theo `type`: heading → giữ tên, level và role; table → tạo `columns[]`, `rows[]` và `n_rows`; các loại còn lại → xử lý như text.

#### 3.2.3. Đọc bảng

Extract duyệt token Markdown theo cấu trúc `thead`, `tr`, `th`, `td`.

`columns[]` giữ tên các cột hiển thị. `rows[]` giữ các hàng dữ liệu. `n_rows` giữ số hàng dữ liệu, không tính header.

Extract không tự chia dòng theo `|`; dấu `|` trong nội dung ô không tạo cột giả. Table element vẫn giữ trường `text` chứa Markdown gốc để truy vết.

Nếu `extract.strip_cell_emphasis=true`, dấu nhấn mạnh trong ô tiêu đề được loại.

#### 3.2.4. Đọc và gán role cho text

Một text block có thể chứa nhiều nhãn liền nhau. Extract cắt block tại mỗi dòng khớp với biểu thức trong `extract.roles`.

Profile SQL có bảy role, chia hai nhóm:

- Tài liệu schema: `table_meaning`, `column_intro`, `relation_hint`, `business_rule`
- SQL sample: `sample_query`, `sample_evidence`, `sample_sql`

Hai nhóm dùng chung một danh sách vì role nhận diện bằng regex; mẫu của nhóm này không khớp nội dung của nhóm kia.

Nhãn được tách khỏi nội dung nhưng vẫn được giữ trong trường `label`. Nếu nhãn và nội dung nằm trong cùng block, nội dung được gộp vào cùng một element. Nếu nhãn đứng riêng còn nội dung nằm ở block khác, extract giữ `text` rỗng.

#### 3.2.5. Tạo element độc lập

Element được đánh ID theo thứ tự đọc: `el_1`, `el_2`, ...

Nếu một block sinh nhiều element, mỗi element nhận một `block_id` có hậu tố thứ tự (`block_5.1`, `block_5.2`).

Tại bước này, extract không tạo: `parent_id`, ancestor `section`/`table`, `relations[]`.

#### 3.2.6. Sinh cảnh báo

Ngoài cảnh báo từ `blocks.py`, extract cảnh báo khi: text không khớp role nào; bảng không có hàng tiêu đề.

### 3.3. Thư viện

- `markdown-it-py`: tách block và đọc bảng ở cấp token.
- `pydantic`: đọc và kiểm tra cấu hình extract.

### 3.4. Đầu ra

Artifact: `<doc_id>.extract.json`. Cấu trúc envelope gồm `schema_version`, `doc_id`, `title`, `source_name`, `warnings[]`, `elements[]`.

### 3.5. Kết quả

| Chỉ số | DOCX | PDF | XLSX |
|---|---|---|---|
| Heading element | 25 | 25 | 19 |
| Table element | 18 | 18 | 0 |
| Text element | 72 | 73 | 72 |
| Tổng element | 115 | 116 | 91 |
| Tổng hàng dữ liệu | 194 | 194 | — |
| Element có `parent_id` | 0 | 0 | 0 |

PDF có thêm một text element không khớp role; element này được giữ và cảnh báo được đưa vào `warnings[]`.

XLSX có 18 element không khớp role — đó là 18 khối code chứa câu SQL, chúng được `link/` ghép vào nhãn `sql:` đứng ngay trước.

### 3.6. Giới hạn hiện tại

- `block_N` và `el_N` phụ thuộc vào vị trí: khi chèn nội dung đầu tài liệu, ID phía sau có thể thay đổi.
- List, quote, code và HTML hiện đi qua nhánh text.
- Extract không diễn giải ý nghĩa cột hoặc quan hệ nghiệp vụ, không ghép nhãn với element khác, không xây dựng hierarchy.

---

## 4. `link/` — Elements thành hierarchy

### 4.1. Đầu vào

Link nhận `<doc_id>.extract.json`. Các element đầu vào độc lập và chưa có `parent_id`, chưa có ancestor.

### 4.2. Nhiệm vụ

#### 4.2.1. Gắn heading cha–con

Hàm `attach_hierarchy()` duyệt element theo thứ tự đọc và duy trì stack heading. Khi gặp heading mới, đóng các heading cùng cấp hoặc sâu hơn. Heading còn lại trên đỉnh stack trở thành cha.

Quy tắc:

- heading section cấp cao nhất có `parent_id=null`;
- heading table nhận section làm cha;
- text và table nhận heading gần nhất làm cha;
- text và table nhận cả ancestor `section` và `table`.

Tên ancestor được gắn theo `role` của heading trong stack, không theo một danh sách vai trò khai sẵn. Vì vậy chặng này không có khoá cấu hình nào và không chứa tên role của một bộ tài liệu cụ thể trong code.

Bốn trường `parent_id`, `section`, `table`, `role` đã đủ để `chunk/` gom nội dung theo từng đơn vị. Một quan hệ dạng `applies_to` nối business rule với heading bảng sẽ nói lại đúng điều mà ancestor `table` đã nói, nên không được tạo.

#### 4.2.2. Ghép nhãn đứng riêng với nội dung sau

Hàm `merge_standalone_labels()` ghép nhãn với text tiếp theo khi: element hiện tại là text có `label`; `text` của element hiện tại rỗng; element tiếp theo là text không có label và không có role; hai element cùng `parent_id`.

Element chứa label giữ nguyên ID, nhận nội dung của element sau và mở rộng `line_end`. Element nội dung dư được loại để linked artifact không chứa hai bản sao cùng một câu.

Nhãn đứng trước một bảng không bị ghép. `"Chi tiết các cột trong bảng:"` là câu dẫn; nuốt vào bảng thì nó dính hàng tiêu đề và hỏng cú pháp Markdown. Nhãn ở lại thành một element text riêng và vẫn vào chunk như một dòng.

#### 4.2.3. Không tạo relationships

Chặng này chỉ dựng cây và ghép nhãn. Diễn giải quan hệ nghiệp vụ — bảng nào nối bảng nào qua cột gì, nhãn nào mô tả object nào — thuộc chặng `graph/` và không tất định như ở đây.

#### 4.2.4. Sinh cảnh báo

Link quét một lượt để lập bảng `parent_id → tập modality của các con`, rồi sinh ba cảnh báo:

| Cảnh báo | Điều kiện |
|---|---|
| element nằm ngoài mọi heading | element không phải heading và không có `parent_id` |
| nhãn rỗng không tìm được nội dung | nhãn có `label`, `text` rỗng, và trong cùng cha không có object nào ngoài text/heading |
| heading cấp sâu nhất không có bảng bên dưới | heading ở cấp sâu nhất mà không có element table nào làm con |

Cảnh báo thứ hai xét theo **cùng cha**, không theo element đứng kề. Ở bản PDF, Docling chèn text vào giữa nhãn và bảng nên chỉ 1 trong 18 nhãn đứng ngay trước bảng của nó; xét theo kề sẽ báo oan 17 lần trên một tài liệu lành.

Cảnh báo thứ ba chỉ chạy khi tài liệu thật sự có element table.

Linked artifact chứa cảnh báo tích lũy của ba chặng.

### 4.3. Thư viện

Link chỉ sử dụng thư viện chuẩn Python (`json`, `collections`, `pathlib`, `sys`). Không dùng regex, không gọi LLM. Chặng này tất định: cùng đầu vào cho ra cùng artifact.

### 4.4. Đầu ra

Artifact: `<doc_id>.linked.json`. Giữ nguyên envelope của extract và thay `elements[]` bằng các element đã gắn hierarchy. Không có `relations[]`.

### 4.5. Kết quả

| Chỉ số | DOCX | PDF | XLSX |
|---|---|---|---|
| Tổng element | 115 | 116 | 73 |
| Root có `parent_id=null` | 7 | 7 | 1 |
| Element không phải root có `parent_id` | 108/108 | 109/109 | 72/72 |
| Element mang ancestor `section` | 108 | 109 | 72 |
| Element mang ancestor cấp hai | 90 | 91 | 54 |
| Nhãn dẫn vào bảng, đứng riêng | 18 | 18 | 0 |
| Cảnh báo do link sinh ra | 0 | 0 | 0 |

Hai bản DOCX và PDF hội tụ về cùng một cây dù Docling xếp phần tử theo thứ tự khác: cây bám vào cấp heading, không bám vị trí kề nhau.

XLSX giảm từ 91 xuống 73 element vì 18 khối code chứa SQL được ghép vào nhãn `sql:`.

### 4.6. Giới hạn hiện tại

- Hierarchy phụ thuộc thứ tự heading trong mảng.
- Ghép nhãn phụ thuộc vị trí: nhãn chỉ ghép được với element đứng ngay sau nó và cùng cha.
- 18 nhãn dẫn vào bảng đứng riêng vĩnh viễn; quan hệ "nhãn này mô tả bảng kia" không được biểu diễn trong artifact.
- `el_N` phụ thuộc vị trí, chưa phải ID ổn định.
- Link không diễn giải quan hệ nghiệp vụ giữa các bảng.

---

## 5. `chunk/` — Elements thành chunk

### 5.1. Đầu vào

Chunk nhận `<doc_id>.linked.json`. Không đọc lại Markdown và không đọc `.extract.json`: element ở đó chưa có `section`/`table`, gom theo đơn vị sẽ ra rỗng.

### 5.2. Nhiệm vụ

#### 5.2.1. Hai chế độ

- `general` — cắt phẳng, mọi chunk cùng một bộ tham số, khớp cái nào trả thẳng cái đó.
- `parent_child` — hai tầng. Con nhỏ, đi vào vector store, dùng để khớp truy vấn. Cha lớn, được trả về cho LLM khi con khớp.

Mỗi bộ tri thức khai khối `chunk` của riêng nó trong `knowledge[]`, nên tài liệu schema và bộ SQL sample dùng hai chế độ khác nhau trong cùng một profile.

#### 5.2.2. Thang cắt

Trong mỗi tầng, cắt theo thang `split_on`, thứ tự trong mảng là thứ tự ưu tiên:

- `heading` — một heading cấp N là một đơn vị nội dung;
- `table_row` — bảng quá dài cắt thành từng nhóm hàng, lặp header;
- `length` — chốt chặn cuối, dùng `RecursiveCharacterTextSplitter` với `separators` khai trong profile và `keep_separator=False`.

Chỉ xuống bậc sau khi bậc trước cho ra chunk vượt `budget.max`. Với `on_overflow: "keep"`, thang dừng ở bậc đầu và độ dài không bị cưỡng chế.

#### 5.2.3. Ngân sách

`budget.unit` nhận `token` hoặc `char`. Với `token`, độ dài đếm bằng chính tokenizer của `embed.dense.model`, không phải ước lượng theo ký tự.

Breadcrumb và ngữ cảnh thừa hưởng được ghép vào sau khi cắt, nên chúng được trừ hao trước: trần thực tế của thang cắt là `budget.max` trừ độ dài phần đầu.

#### 5.2.4. Tầng con lọc theo role

`child_roles` khai element nào được giữ ở tầng con. Với bộ SQL sample, `child_roles: ["sample_query"]` nghĩa là con chỉ gồm câu hỏi nên vector của nó thuần câu hỏi, không bị pha loãng bởi evidence và câu SQL; cha vẫn là cả mẫu.

#### 5.2.5. Ngữ cảnh

- `breadcrumb` — đường dẫn `tài liệu > section > đơn vị` prepend vào đầu chunk.
- `inherit.from_roles` — mảnh thứ hai trở đi của một đơn vị bị cắt thừa hưởng nội dung của role được khai.
- `restore_labels` — dựng lại nhãn mà extract đã cắt.

#### 5.2.6. Định danh chunk

`chunk_id` băm nội dung trong phạm vi một tài liệu, không băm vị trí. Chèn một đơn vị ở đầu tài liệu không đổi ID của các chunk phía sau.

`content_hash` băm `page_content` thật sự được lưu, kể cả breadcrumb.

### 5.3. Thư viện

- `langchain-text-splitters`: `RecursiveCharacterTextSplitter` cho bậc `length`.
- `langchain-core`: biểu diễn Document.
- `transformers`: tokenizer để đếm token.

### 5.4. Đầu ra

- `<doc_id>.chunks.jsonl` — chunk đi vào vector store.
- `<doc_id>.parents.jsonl` — chỉ có ở chế độ `parent_child`.

### 5.5. Kết quả

| Chỉ số | DOCX | PDF | XLSX |
|---|---|---|---|
| Chế độ | general | general | parent_child |
| Chunk | 18 | 18 | 18 con + 18 cha |
| Token con min / p50 / max | 176 / 488 / 1349 | 166 / 481 / 1348 | 28 / 39 / 52 |
| Token cha min / p50 / max | — | — | 232 / 374 / 706 |
| Đơn vị bị cắt nhỏ | 0 | 0 | 0 |
| Chunk vượt trần 2048 | 0 | 0 | 0 |

### 5.6. Giới hạn hiện tại

- Không có overlap giữa các chunk khi cắt theo cấu trúc; `budget.overlap` chỉ có tác dụng ở bậc `length`.
- Không có `prev_chunk_id`/`next_chunk_id` để nới ngữ cảnh khi truy hồi.
- `on_underflow` chỉ có `keep` và `drop`, chưa gộp được chunk quá ngắn.
- Trần token chỉ cảnh báo, không cưỡng chế.

---

## 6. `embed/` — Chunk thành dense vector

### 6.1. Đầu vào

Embed nhận `<doc_id>.chunks.jsonl`.

### 6.2. Nhiệm vụ

- Nạp embedding model và tokenizer. Model nạp qua `HuggingFaceEmbeddings` của LangChain, nhưng giữ tay nắm tới `SentenceTransformer` bên dưới vì đó là chỗ duy nhất lấy được tokenizer thật và `max_seq_length` thật.
- Kiểm tra số token bằng đúng tokenizer của model, với `add_special_tokens=True` vì `[CLS]`/`[SEP]` cũng chiếm chỗ trong context.
- Từ chối chunk vượt context limit. Context limit là giá trị nhỏ hơn giữa `max_seq_length` của model và `embed.dense.max_tokens` của profile. Chunk vượt limit bị từ chối kèm hướng dẫn sửa ở chặng chunk, không tự cắt cụt.
- Embedding `page_content` thành dense vector, chuẩn hoá L2 theo `embed.dense.normalize`.
- Xử lý theo batch. SentenceTransformer tự gom batch theo độ dài, chỉ cần truyền `batch_size` từ profile.
- Giữ mapping `chunk_id → vector` trong artifact riêng.

Artifact tách khỏi chặng `index` vì embed là phần đắt nhất của pipeline còn upsert thì rẻ: đổi vector store không phải embed lại, và `verify` soi được vector trước khi chúng vào store.

### 6.3. Thư viện

- `langchain-huggingface`, `sentence-transformers`: nạp model và mã hoá.
- `transformers`: tokenizer.
- `numpy`: ma trận vector và artifact `.npz`.

### 6.4. Đầu ra

`<doc_id>.vectors.npz` chứa `ids`, `vectors` và tên model. Đọc lại bằng model khác tên sẽ bị từ chối.

### 6.5. Kết quả

| Chỉ số | DOCX | PDF | XLSX (con) |
|---|---|---|---|
| Vector | 18 | 18 | 18 |
| Chiều | 1024 float32 | 1024 float32 | 1024 float32 |
| Token min / p50 / max | 178 / 490 / 1351 | 168 / 483 / 1350 | 30 / 41 / 54 |
| Context limit | 2048 | 2048 | 2048 |
| Chuẩn L2 | 1.0000 | 1.0000 | 1.0000 |
| Vector NaN/Inf | 0 | 0 | 0 |

Model: `AITeamVN/Vietnamese_Embedding`.

Số token ở đây lớn hơn số ở chặng chunk đúng hai đơn vị vì tính cả token đặc biệt.

### 6.6. Giới hạn hiện tại

- Chỉ hỗ trợ model chạy được qua `SentenceTransformer`.
- Không có cache: chunk không đổi vẫn được embed lại khi chạy lại.

---

## 7. `index/` — Đưa chunk vào hệ thống tìm kiếm

### 7.1. Đầu vào

`<doc_id>.chunks.jsonl`, `<doc_id>.vectors.npz`, và `<doc_id>.parents.jsonl` nếu có. Số chunk và số vector phải khớp, lệch thì dừng.

### 7.2. Nhiệm vụ

Index tạo hai đường tìm kiếm trên **cùng một tập point**.

**Dense index** — named vector `dense`, khoảng cách cosine, vector lấy từ `.vectors.npz` để tìm theo ngữ nghĩa.

**Sparse/BM25 index** — named sparse vector `bm25`, dựng trực tiếp từ `page_content` để tìm từ khóa chính xác.

Hai đường nằm chung point nên `chunk_id` của chúng luôn khớp nhau; không có cách nào để hai chỉ mục lệch tập tài liệu. Đó là lý do không tách BM25 ra một store riêng dù nó rẻ hơn.

`Modifier.IDF` là bắt buộc với sparse vector do FastEmbed sinh ra: bộ mã hoá cố tình bỏ phần IDF khỏi trọng số để Qdrant tính lấy trên toàn collection. Thiếu cờ này thì điểm BM25 sai công thức mà không có lỗi nào báo.

Point ID suy từ `chunk_id`, mà `chunk_id` băm theo nội dung, nên chạy lại trên cùng dữ liệu ghi đè đúng point cũ và không nhân đôi.

Payload giữ `text` nguyên văn cộng toàn bộ metadata trải phẳng. Ở chế độ `parent_child`, payload còn có `parent_text` là nội dung đầy đủ của cha: quan hệ ở đây là 1-1 nên không có gì bị nhân bản, và truy hồi chỉ tốn một vòng gọi — khớp bằng câu hỏi rồi trả về cả mẫu, không phải tra thêm docstore.

### 7.3. Thư viện

- `qdrant-client`: tạo collection, upsert, truy vấn.
- `fastembed`: sinh sparse vector BM25.

### 7.4. Đầu ra

Collection trong Qdrant, một collection cho mỗi bộ tri thức trong mỗi dự án. Hai dự án không dùng chung collection nào.

### 7.5. Kết quả

| Collection | Point | Nguồn | Chế độ chunk | `parent_text` |
|---|---|---|---|---|
| `sqlp1__docs` | 18 | `.docx` | general | không |
| `sqlp1__sql` | 18 | `.xlsx` | parent_child | có |
| `sqlp2__docs` | 18 | `.pdf` | general | không |
| `sqlp2__sql` | 18 | `.xlsx` | parent_child | có |

Cả bốn collection đều có `dense` 1024 chiều cosine và `bm25` với `modifier=idf`. Giao của tập collection dự án 1 và dự án 2 là rỗng.

Ví dụ một point trong `sqlp1__sql`: con 120 ký tự (chỉ câu hỏi) → cha 1.613 ký tự (cả mẫu gồm query, evidence và SQL).

### 7.6. Giới hạn hiện tại

- Chỉ hỗ trợ Qdrant.
- Chunk đổi nội dung sinh point mới, point cũ thành rác; phải dùng `--recreate` khi đổi cách chunk.
- `parent_text` nằm trong payload của con nên chỉ hợp với quan hệ 1-1 hoặc ít con mỗi cha; nhiều con mỗi cha sẽ nhân bản nội dung.

---

## 8. `verify/` — Kiểm tra index đã dùng được chưa

### 8.1. Kiểm tra tính toàn vẹn

Ba nguồn phải khớp nhau từng `chunk_id`: `.chunks.jsonl`, `.vectors.npz`, và point trong Qdrant. Lệch giữa ba nguồn là kiểu hỏng không tự lộ ra lúc chạy: truy vấn vẫn trả về kết quả, chỉ là thiếu mất vài đơn vị, hoặc trả về đơn vị có vector nhưng không còn text.

Các phép kiểm:

- Không có `chunk_id` trùng.
- Không có chunk rỗng.
- Không có chunk vượt `budget.max`.
- Số vector bằng số chunk.
- Vector có đúng dimension.
- Vector không chứa NaN hoặc Infinity.
- Dense index và sparse index có cùng tập `chunk_id`. Vì hai chỉ mục nằm chung point, phép này được kiểm bằng cách xác nhận mỗi point mang đủ cả hai vector.
- Mỗi record vẫn giữ được `page_content` và metadata cần thiết: `chunk_id`, `doc_id`, `table_name`, `section`, `element_ids`, `line_start`, `line_end`, `n_tokens`.

Mã thoát khác 0 khi có lỗi, để nối được vào CI.

**Kết quả:** cả bốn bộ tri thức của hai dự án đều toàn vẹn.

| Bộ tri thức | Chunk | Vector | Kết luận |
|---|---|---|---|
| Dự án 1 — `schema_docx` | 18 | 18 | toàn vẹn |
| Dự án 1 — `sql_sample` | 18 | 18 | toàn vẹn |
| Dự án 2 — `schema_pdf` | 18 | 18 | toàn vẹn |
| Dự án 2 — `sql_sample` | 18 | 18 | toàn vẹn |

### 8.2. Chấm điểm truy hồi

Một câu hỏi được truy hồi trên hai đường của dự án, mỗi đường một trần khác nhau:

| Đường | Trần | Collection | Cách suy ra tên bảng |
|---|---|---|---|
| Tài liệu | top-5 | `..__docs` | `table_name` của chunk |
| SQL sample | top-3 | `..__sql` | tập bảng của mẫu khớp được |

Điểm của một câu: `(recall_docs@5 + recall_sql@3) / 2`. Hai vế đều là "số bảng gold tìm được / tổng bảng gold". Chia đôi để điểm nằm trong [0, 1]; báo cáo cả hai vế riêng vì chúng hỏng theo hai kiểu khác nhau — vế tài liệu yếu là truy hồi kém, vế sample yếu là bộ mẫu chưa phủ dạng câu hỏi.

**Chặn rò rỉ.** Tập `dev.json` và bộ SQL sample đem đi index là cùng 18 dòng. Truy hồi vế sample sẽ luôn tìm thấy chính câu hỏi đang hỏi, và mẫu đó tự khai đáp án. Điểm lúc đó là điểm trí nhớ, không phải điểm truy hồi. Vì vậy mẫu trùng `test_case_id` với câu hỏi bị loại khỏi kết quả trước khi chấm.

**Kết quả trên tập dev, chế độ `rrf`:**

| | Dự án 1 (DOCX) | Dự án 2 (PDF) |
|---|---|---|
| recall tài liệu@5 | 0.704 | 0.713 |
| complete tài liệu@5 | 0.389 | 0.389 |
| recall SQL sample@3 | 0.838 | 0.838 |
| **Điểm tổng** | **0.771** | **0.775** |

Hai dự án chênh nhau 0.004 — hai định dạng của cùng một tài liệu cho kết quả truy hồi tương đương, đúng như phần `parse` và `link` đã cho thấy chúng hội tụ về cùng một cấu trúc.

**Vế SQL sample mạnh hơn vế tài liệu** (0.838 so với 0.704). Câu hỏi trong bộ mẫu gần nhau về cách diễn đạt nên tìm mẫu tương tự dễ hơn tìm đúng bảng trong tài liệu schema. Hai câu SQL_006 và SQL_015 có `sql@3 = 0` vì cả ba mẫu gần nhất đều không dùng bảng mà chúng cần.

### 8.3. Chỉnh tham số truy hồi

`verify/retrieval.py` quét 32 cấu hình trên bốn trục: `mode` (dense/sparse/rrf/wrrf), `candidate_k`, `rrf_k`, `weights`.

Dev dùng để **chọn tham số**, không dùng để báo cáo. Chốt xong tham số bằng dev thì chạy `test.json` một lần duy nhất để lấy số cuối cùng.

**Kết quả quét, top-5:**

| mode | candidate_k | rrf_k | weights | complete@5 | recall@5 | mrr |
|---|---|---|---|---|---|---|
| rrf | 50 | server | — | 0.389 | 0.704 | 0.889 |
| rrf | 20 | server | — | 0.389 | 0.704 | 0.861 |
| wrrf | 20 | 10 | 0.5/0.5 | 0.333 | 0.685 | 0.852 |
| sparse | — | — | — | 0.333 | 0.676 | 0.861 |
| dense | — | — | — | 0.278 | 0.634 | 0.806 |

**Ảnh hưởng của `k`:**

| top-k | complete | recall |
|---|---|---|
| 5 | 0.389 | 0.704 |
| 8 | 0.500 | 0.810 |
| 10 | 0.611 | 0.880 |

**Kết luận.** RRF phía server thắng mọi biến thể weighted; không có bộ trọng số nào vượt được 50/50 và `rrf_k` gần như không ảnh hưởng, nghĩa là hai nhánh đóng góp cân bằng. Nút thắt không nằm ở công thức fusion mà ở `k`: phần lớn câu hỏi cần 3–4 bảng, lấy 5 trên tổng 18 bảng thì gần như không có chỗ sai. Nới lên 10 kéo `complete` từ 0.389 lên 0.611.

### 8.4. Giới hạn hiện tại

- Chưa chạy chấm điểm trên `test.json`; mọi số trong báo cáo đo trên `dev`.
- Reranker khai trong profile nhưng chưa nối vào đường đo.
- Vế SQL sample chấm bằng tập bảng của mẫu, tức một chỉ báo thay thế: mẫu dùng cùng bộ bảng thì gần như chắc chắn minh hoạ cùng kiểu JOIN, nhưng không có gì bảo đảm nó là mẫu tốt nhất cho câu hỏi.
- Bộ đo chỉ có 18 câu dev và 15 câu test; chênh lệch dưới 0.05 giữa hai cấu hình nằm trong nhiễu.

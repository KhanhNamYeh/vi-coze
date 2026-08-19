# `parse/` — tài liệu gốc thành Markdown

## Đầu vào

`.docx` và `.pdf` — khai ở `parse.suffixes` trong `config/sql.json`, mặc định
đặt tại `data/raw/sql/`.

## Nhiệm vụ

### Đặt định danh tài liệu

Tạo `doc_id` từ slug bỏ dấu và đuôi nguồn:

```text
Mô tả bảng BĐS (NEW).docx
→ mo_ta_bang_bds_new__docx
```

Đuôi nguồn nằm trong `doc_id` để bản DOCX và PDF của cùng tài liệu không ghi đè
artifact của nhau.

Trước khi nhận file, parser quét thư mục chứa nguồn. Nếu hai file khác nhau cho
ra cùng `doc_id`, pipeline dừng và báo tên cả hai file.

### Nhận diện định dạng và chọn loader

Nhận diện định dạng theo đuôi file và đối chiếu với `parse.suffixes`. Đuôi không
có trong danh sách bị từ chối ngay, kèm danh sách các đuôi được khai.

Chọn loader:

```text
.pdf  → pdf_parse  → Docling
.docx → docx_parse → MarkItDown/Mammoth
```

Docling nặng nên chỉ được import khi thật sự gặp `.pdf`.

### Mở và giải mã file

MarkItDown gọi Mammoth đọc OOXML và trả Markdown thô.

Docling chạy mô hình nhận diện layout với `do_table_structure=True` và trả về
`DoclingDocument` — một cây object có item, marker và bảng, không phải text
Markdown đã hoàn chỉnh.

### Khôi phục cấp bậc tiêu đề

Mỗi loader có một bộ luật riêng vì hai định dạng hỏng theo hai kiểu khác nhau.

DOCX: tên bảng dùng style `normal`, nên MarkItDown xuất thành bullet in đậm:

```text
* 1. **Bảng X**
```

`docx_parse.restructure()` nâng dòng này thành:

```text
## Bảng X
```

Luật nhận diện lấy từ `parse.table_heading` trong profile. Nhóm bắt `name` được
đưa thẳng vào heading. Nội dung trước heading cấp một đầu tiên được coi là bìa
hoặc mục lục và bị bỏ; link neo của mục lục cũng bị loại.

PDF: đọc thẳng object model của Docling, không đi qua
`export_to_markdown()` cho toàn tài liệu. Docling có thể gán mọi tiêu đề
`level=1` và đọc nhầm tên bảng thành list item, nhưng số thứ tự vẫn còn trong
`text` hoặc `item.marker`.

Số quyết định cấp bậc:

```text
1.   → # section
1.1. → ## table
```

Quy tắc được áp dụng cho mọi item, không phụ thuộc nhãn Docling đã gán. Nội dung
trước tiêu đề đánh số đầu tiên được coi là bìa/mục lục và bị bỏ.

### Nối bảng PDF bị ngắt trang

Docling cắt bảng theo ranh giới trang; phần sau không còn dòng tiêu đề thật. Hai
table item liền kề được coi là một bảng bị ngắt và được nối thành một bảng
Markdown.

Logic này nằm trong `parse/` vì phải chạy trước khi tạo canonical Markdown. Nếu
để tới extract, hàng dữ liệu đầu của phần sau đã bị hiểu nhầm thành tên cột.

### Làm sạch văn bản

DOCX và PDF dùng chung `sanitize()`:

- chuẩn hóa Unicode NFC;
- bỏ ký tự vô hình;
- bỏ HTML comment và các thẻ HTML được nhận diện;
- cảnh báo liệt kê đúng thẻ đã bỏ;
- bỏ dải gạch ngang ngăn mục;
- sửa lỗi gõ của tài liệu nguồn theo `parse.replacements`;
- cảnh báo dòng nghi prompt injection nhưng không xóa nội dung;
- bỏ khoảng trắng cuối dòng, co khoảng trắng thừa và giới hạn dòng trống liên
  tiếp.

Markdown ngắn hơn 50 ký tự bị từ chối để tránh đưa tài liệu rỗng hoặc PDF scan
chưa OCR sang chặng sau.

### Giữ metadata tối thiểu

Parse giữ trong bộ nhớ:

```text
doc_id
title
source_name
warnings[]
```

Metadata này được truyền nội bộ sang extract. Parse không ghi file metadata
riêng.

## Thư viện

`markitdown[docx]` — DOCX thành Markdown · `docling` — PDF thành object model,
extra `pdf` · `langchain-core` — `Document` và metadata · `pydantic` — đọc
profile.

## Đầu ra — `<doc_id>.md`

Artifact duy nhất của parse:

```text
data/processed/sql/<doc_id>.md
```

Không tạo `DocumentIR`, không tạo `blocks[]` và không tạo metadata sidecar.

Ví dụ:

```markdown
# Danh mục dùng chung

## Bảng V_USER_PRECINCT_PERMISSION

Ý nghĩa của bảng: Lưu trữ quyền truy cập của user theo phường/xã.

| **Tên cột** | **Kiểu dữ liệu** | **Mô tả** |
| --- | --- | --- |
| USER_NAME | VARCHAR2 | Mã user |
```

## Kết quả — hai định dạng hội tụ về cấu trúc chính

| Chỉ số | DOCX | PDF |
|---|---:|---:|
| Heading section | 7 | 7 |
| Heading table | 18 | 18 |
| Bảng | 18 | 18 |
| Tổng hàng dữ liệu | 194 | 194 |
| Thời gian convert quan sát | dưới 1 giây | khoảng 75 giây |

PDF phải chạy model layout nên chậm hơn nhiều. Thời gian trên là số quan sát với
tài liệu mẫu, không phải SLA.

## Giới hạn hiện tại

- Không giữ bbox, số trang, ảnh, figure, caption, header/footer hoặc tài sản
  gốc. Với PDF, đây là mất mát so với object model Docling.
- Nhận diện định dạng theo đuôi file, chưa đọc magic bytes.
- Có bản DOCX thì nên ưu tiên DOCX vì nhanh hơn và không cần model layout.
- Chạy riêng parse chỉ tạo `.md`; muốn giữ đầy đủ warnings trong extract phải
  chạy pipeline liền mạch để metadata được truyền trong bộ nhớ.

# `extract/` — Markdown thành structured elements độc lập

## Đầu vào

`<doc_id>.md` do parse sinh ra, nằm tại `data/processed/sql/`.

## Nhiệm vụ

### `blocks.py` — cắt block

Dùng `markdown-it-py` với CommonMark và bảng GFM để phát hiện các block cấp
ngoài cùng:

```text
heading
paragraph
list
table
quote
code
html
```

Không dùng regex để tách Markdown, nhờ đó xử lý đúng code fence, heading gạch
dưới, danh sách lồng và dấu `\|` được escape trong ô bảng.

Xác định `line_start`/`line_end`, 1-based trên file `.md`, từ `token.map`.

Tạo ID block theo thứ tự đọc:

```text
block_1, block_2, ...
```

Thứ tự đọc chính là thứ tự của mảng, không có field `order` riêng.

Gán vai trò heading từ `extract.heading_roles`:

```text
#  → section
## → table
```

Extract không đọc `chunk.headers`.

Kiểm tra cấu trúc và sinh cảnh báo khi:

- tài liệu không có block;
- thiếu hẳn một heading role đã khai;
- heading có level không nằm trong `extract.heading_roles`.

Block chỉ tồn tại trong bộ nhớ. Không ghi `.blocks.json`, vì đây là dữ liệu có
thể dựng lại trực tiếp từ `.md`.

Có thể chạy lệnh sau để soi cấu trúc mà không ghi artifact:

```powershell
uv run python -m src.branch_sql.offline.extract.blocks <doc_id>.md
```

### `block_extract.py` — đọc nội dung

Chọn bộ xử lý theo `type` của block:

```text
heading → giữ tên, level, role
table   → columns[] + rows[] + n_rows
còn lại → text có label/role
```

### Đọc bảng

Đi trên token Markdown:

- `thead` phân biệt hàng tiêu đề;
- `tr` mở một hàng;
- `th`/`td` xác định ô;
- `columns[]` giữ tên cột;
- `rows[]` giữ dữ liệu;
- `n_rows` giữ số hàng dữ liệu.

Không tự tách theo dấu `|`, nên dấu `\|` trong nội dung ô không tạo cột giả.

Bảng vẫn giữ `text` là Markdown gốc để không phải render ngược từ
`columns[]`/`rows[]`.

Nếu `extract.strip_cell_emphasis=true`, dấu nhấn mạnh trong ô tiêu đề được bỏ
bằng token con:

```text
**Tên cột** → Tên cột
```

### Đọc và gán role cho text

Một text block có thể chứa nhiều nhãn liền nhau. Extract cắt lại tại mỗi dòng
khớp regex trong `extract.roles`.

Bốn role của profile SQL:

```text
table_meaning
column_intro
relation_hint
business_rule
```

Nhãn được tách khỏi nội dung nhưng vẫn được giữ:

```text
Mối liên kết: qua cột CODE
```

trở thành:

```json
{
  "role": "relation_hint",
  "label": "Mối liên kết:",
  "text": "qua cột CODE"
}
```

Nhãn đứng riêng mà nội dung nằm trong cùng block vẫn được gộp vào `text`. Nếu
nội dung nằm ở block khác, extract để `text` rỗng; link mới ghép hoặc tạo quan
hệ.

Giữ `line_start`/`line_end` cho từng element, kể cả khi một block bị cắt thành
nhiều đoạn. Khoảng dòng phủ cả dòng nhãn và dòng nội dung.

Khi một block sinh nhiều element, `block_id` nhận hậu tố:

```text
block_5 → block_5.1, block_5.2
```

### Tạo element độc lập

Extract gắn ID theo thứ tự đọc:

```text
el_1, el_2, ...
```

Extract không tạo:

```text
parent_id
section/table ancestors
caption_of
relations[]
```

Toàn bộ hierarchy và quan hệ thuộc `link/`.

### Sinh cảnh báo

Ngoài cảnh báo block, extract cảnh báo:

- text không khớp role nào trong `extract.roles`;
- bảng không có hàng tiêu đề.

Cảnh báo parse được truyền vào và gom chung trong `warnings[]`.

## Thư viện

`markdown-it-py` — tách block và đọc bảng ở mức token · `pydantic` — đọc
`extract.heading_roles`, `extract.roles` và `strip_cell_emphasis`.

## Đầu ra — `<doc_id>.extract.json`

```json
{
  "schema_version": "1.0",
  "doc_id": "mo_ta_bang_bds_new__docx",
  "title": "Mô tả bảng BĐS (NEW)",
  "source_name": "Mô tả bảng BĐS (NEW).docx",
  "warnings": [],
  "elements": []
}
```

Ví dụ heading element:

```json
{
  "block_id": "block_2",
  "modality": "heading",
  "level": 2,
  "role": "table",
  "text": "Bảng V_USER_PRECINCT_PERMISSION",
  "line_start": 3,
  "line_end": 3,
  "id": "el_2"
}
```

Ví dụ table element:

```json
{
  "block_id": "block_4",
  "modality": "table",
  "text": "| **Tên cột** | **Kiểu dữ liệu** | **Mô tả** |\n| --- | --- | --- |\n...",
  "columns": ["Tên cột", "Kiểu dữ liệu", "Mô tả"],
  "rows": [["USER_NAME", "VARCHAR2", "Mã user"]],
  "n_rows": 1,
  "line_start": 8,
  "line_end": 17,
  "id": "el_5"
}
```

## Kết quả

| Chỉ số | DOCX | PDF |
|---|---:|---:|
| Heading element | 25 | 25 |
| Table element | 18 | 18 |
| Text element | 72 | 73 |
| Tổng element | 115 | 116 |
| Tổng hàng dữ liệu | 194 | 194 |
| Element có `parent_id` | 0 | 0 |

PDF có thêm một text element không khớp role. Element được giữ nguyên và cảnh
báo được đưa vào `warnings[]`.

## Giới hạn hiện tại

- `block_N` và `el_N` phụ thuộc vị trí; chèn nội dung ở đầu tài liệu làm ID phía
  sau thay đổi.
- List, quote, code và HTML đi qua nhánh text; output hiện không giữ modality
  riêng cho từng loại này.
- Không diễn giải ý nghĩa từng cột hoặc quan hệ nghiệp vụ trong extract.
- Không ghép nhãn với element khác tại chặng này.

# `link/` — elements thành hierarchy và relationships

## Đầu vào

`<doc_id>.extract.json` với envelope:

```text
schema_version
doc_id
title
source_name
warnings[]
elements[]
```

Mỗi element đầu vào độc lập, chưa có `parent_id`, `section`, `table` hoặc
relations.

## Nhiệm vụ

### Gắn heading cha–con

`attach_hierarchy()` quét element theo thứ tự đọc và giữ stack các heading đang
mở.

Khi gặp heading mới có level nhỏ hơn hoặc bằng heading trên đỉnh stack, các
heading cùng cấp hoặc sâu hơn được đóng.

Mỗi element nhận `parent_id` là heading cha gần nhất. Tên các heading tổ tiên
được gắn dưới khóa role tương ứng.

Với profile SQL:

```json
{
  "parent_id": "el_2",
  "section": "Danh mục dùng chung",
  "table": "Bảng V_USER_PRECINCT_PERMISSION"
}
```

Heading bảng nhận section làm tổ tiên. Text và table element bên trong nhận cả
section và table.

### Ghép nhãn đứng riêng với nội dung sau nó

`merge_standalone_labels()` ghép khi:

- element hiện tại là text có `label` nhưng `text` rỗng;
- element ngay sau là text không có `label` và không có `role`;
- hai element có cùng `parent_id`.

Nhãn giữ nguyên ID. Nội dung của element sau được đưa vào nhãn,
`line_end` được mở rộng và element nội dung dư bị bỏ để linked output không giữ
hai bản sao cùng một câu.

Nếu sau nhãn là object như table, link không nhập hai element. Quan hệ được biểu
diễn bằng `caption_of`.

### Tạo `caption_of`

Nhãn rỗng và object được gom theo `parent_id`. Các nhãn được ghép với object
cùng cha theo thứ tự trong nhóm.

Không yêu cầu nhãn đứng sát object. Vì vậy PDF vẫn nối đúng khi Docling xếp:

```text
column_intro → relation_hint → business_rule → table
```

Relation:

```json
{
  "type": "caption_of",
  "source": "el_4",
  "target": "el_5",
  "confidence": 0.9,
  "rule": "same_parent"
}
```

Nhãn thừa không bị gán bừa; `check()` giữ lại và cảnh báo.

### Nối `relation_hint` và `business_rule` với bảng hiện tại

`applies_to()` đi ngược `parent_id` đến heading gần nhất có `role="table"`.

```json
{
  "type": "applies_to",
  "source": "el_7",
  "target": "el_2",
  "confidence": 1.0,
  "rule": "table_ancestor"
}
```

Chỉ hai role sau tham gia:

```text
relation_hint
business_rule
```

### Nối tới bảng được nhắc tên

`_aliases()` tạo bí danh từ heading:

- luôn giữ tên heading đầy đủ;
- giữ token viết hoa, có chữ số hoặc dấu gạch dưới;
- token chỉ được giữ khi xuất hiện ở đúng một heading.

Token chung xuất hiện ở nhiều heading bị loại. Regex có biên từ để `PRECINCT`
không khớp lọt trong `V_USER_PRECINCT_PERMISSION`.

Link bỏ relation tự trỏ và relation trỏ về tổ tiên của chính element.

```json
{
  "type": "refers_to",
  "source": "el_20",
  "target": "el_2",
  "confidence": 0.7,
  "rule": "heading_alias"
}
```

### Nối tới cột được nhắc tên

Extract không tạo column element. `refers_to_columns()` lấy ô đầu của mỗi row
làm tên cột, tìm tên đó trong `relation_hint` hoặc `business_rule`, rồi trỏ tới
table element chứa cột.

Tên cột được giữ trong `rule`:

```json
{
  "type": "refers_to",
  "source": "el_6",
  "target": "el_5",
  "confidence": 0.9,
  "rule": "column:CODE"
}
```

Cách này không mở rộng `elements[]` bằng column node nhưng vẫn giữ được bảng và
tên cột liên quan.

### Tạo `continuation_of`

Hai heuristic hiện có:

- table có `columns[]` rỗng và đứng sau một table được coi là phần nối của bảng
  trước — confidence `0.8`;
- text không có role và đóng nhiều ngoặc hơn mở được coi là đuôi câu bị ngắt —
  confidence `0.6`.

Relation trỏ từ mảnh sau về mảnh trước:

```json
{
  "type": "continuation_of",
  "source": "el_20",
  "target": "el_19",
  "confidence": 0.8,
  "rule": "broken:table"
}
```

Đây là suy đoán, nên mọi `continuation_of` đều sinh cảnh báo để kiểm tra bằng
mắt.

### Đánh số quan hệ

Relations được tạo theo thứ tự builder rồi đánh ID:

```text
r_1, r_2, ...
```

Các loại hiện có:

| Type | Source → target | Confidence |
|---|---|---:|
| `caption_of` | nhãn rỗng → object cùng cha | `0.9` |
| `continuation_of` | mảnh sau → mảnh trước | `0.8` hoặc `0.6` |
| `applies_to` | role nghiệp vụ → heading bảng hiện tại | `1.0` |
| `refers_to` | role nghiệp vụ → heading được nhắc tên | `0.7` |
| `refers_to` | role nghiệp vụ → table chứa cột được nhắc | `0.9` |

### Sinh cảnh báo

Link bổ sung cảnh báo khi:

- nhãn rỗng không tìm được object cùng cha;
- element không phải heading nằm ngoài mọi heading;
- có `continuation_of` cần soi lại;
- tài liệu không có heading nên không tạo được alias.

Warnings của parse và extract vẫn được giữ. Linked artifact có danh sách cảnh
báo tích lũy của cả ba chặng.

Link làm việc trên bản sao của `elements[]`, không sửa object extract đầu vào.

## Thư viện

Thư viện chuẩn Python: `json`, `re`, `collections`, `pathlib`. Link không gọi
LLM và không cần model ngoài.

## Đầu ra — `<doc_id>.linked.json`

Giữ envelope extract, thay `elements[]` bằng bản đã gắn hierarchy và thêm
`relations[]`:

```json
{
  "schema_version": "1.0",
  "doc_id": "mo_ta_bang_bds_new__docx",
  "title": "Mô tả bảng BĐS (NEW)",
  "source_name": "Mô tả bảng BĐS (NEW).docx",
  "warnings": [],
  "elements": [
    {
      "id": "el_7",
      "parent_id": "el_2",
      "section": "Danh mục dùng chung",
      "table": "Bảng V_USER_PRECINCT_PERMISSION"
    }
  ],
  "relations": [
    {
      "id": "r_1",
      "type": "caption_of",
      "source": "el_4",
      "target": "el_5",
      "confidence": 0.9,
      "rule": "same_parent"
    }
  ]
}
```

## Kết quả

| Quan hệ | DOCX | PDF |
|---|---:|---:|
| `caption_of` | 18 | 18 |
| `applies_to` | 36 | 36 |
| `refers_to` | 36 | 36 |
| `continuation_of` | 0 | 1 |
| Tổng relation | 90 | 91 |
| Element có `parent_id` | 115/115 | 116/116 |

PDF có một `continuation_of`; relation được giữ cùng cảnh báo thay vì tự động
gộp dữ liệu.

## Giới hạn hiện tại

- `parent_id` và ancestor phụ thuộc thứ tự heading trong mảng.
- Ghép nhãn với text chỉ xét element ngay sau.
- `caption_of` ghép theo thứ tự trong cùng parent; lệch số lượng sẽ để lại
  orphan warning.
- Column relation giả định tên cột nằm ở ô đầu mỗi row và target vẫn là table
  element.
- Alias và tên cột hiện được so khớp phân biệt hoa/thường.
- `continuation_of` là heuristic, không phải khẳng định chắc chắn.
- `el_N` và `r_N` phụ thuộc vị trí, chưa phải ID ổn định theo nội dung.

# Luồng cuối cùng

```text
parse/
File → canonical Markdown

extract/
Markdown → independent structured elements

link/
Elements → parent-child và relationships
```

Chạy toàn bộ luồng:

```powershell
uv run python -m src.branch_sql.offline "Mô tả bảng BĐS (NEW).docx"
```

Pipeline chỉ ghi ba artifact trong `data/processed/sql/`:

```text
<doc_id>.md
<doc_id>.extract.json
<doc_id>.linked.json
```

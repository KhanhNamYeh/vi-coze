# SQL document pipeline

Luồng offline của `src/branch_sql` chỉ gồm:

```text
data/raw/sql/
  → parse
  → extract
  → link
  → data/processed/sql/
```

## Trách nhiệm từng chặng

### `parse/`

```text
PDF/DOCX
→ đọc định dạng
→ sửa lỗi cấu trúc đặc thù
→ làm sạch
→ canonical Markdown
```

Việc nối bảng PDF bị ngắt trang và phục hồi heading diễn ra tại đây vì phải hoàn
tất trước khi tạo Markdown. Artifact duy nhất là `<doc_id>.md`; không có
`DocumentIR` hay file metadata riêng. Metadata tối thiểu chỉ được truyền trong
bộ nhớ sang `extract`.

### `extract/`

Đọc Markdown bằng `markdown-it-py`, tách heading, paragraph, list và table; bảng
được chuyển thành `columns[]` và `rows[]`. Text giữ `label`, `role`, `text`; mọi
element giữ `line_start`, `line_end`.

Extract chỉ tạo các element độc lập. Không tạo `parent_id`, ancestor
`section`/`table` hay quan hệ giữa element.

Artifact `<doc_id>.extract.json`:

```json
{
  "schema_version": "1.0",
  "doc_id": "...",
  "title": "...",
  "source_name": "...",
  "warnings": [],
  "elements": []
}
```

Vai trò heading thuộc cấu hình extract:

```json
{
  "extract": {
    "heading_roles": {
      "1": "section",
      "2": "table"
    }
  }
}
```

### `link/`

Nhận `elements[]` và:

- gắn heading cha–con;
- gắn element vào tổ tiên theo vai trò heading (`section`, `table`, ...);
- ghép nhãn đứng riêng với block text theo sau.

Artifact là `<doc_id>.linked.json`. Chặng này KHÔNG tạo `relations[]`: diễn giải
quan hệ nghiệp vụ giữa các bảng thuộc `graph/`, và không tất định như ở đây.

Không có khoá cấu hình nào. `attach_hierarchy` suy tập vai trò tổ tiên từ chính
các heading có trong tài liệu, nên hồ sơ đặt tên vai trò là gì cũng chạy.

## Dữ liệu và cách chạy

File nguồn đặt trong `data/raw/sql/`. Tất cả artifact có thể sinh lại nằm trong
`data/processed/sql/`.

```bash
uv run python -m src.branch_sql.offline "Mô tả bảng BĐS (NEW).docx"
```

Chạy riêng từng chặng:

```bash
uv run python -m src.branch_sql.offline.parse.doc_parse "Mô tả bảng BĐS (NEW).docx"
uv run python -m src.branch_sql.offline.extract.block_extract mo_ta_bang_bds_new__docx
uv run python -m src.branch_sql.offline.link.hierarchy mo_ta_bang_bds_new__docx
```

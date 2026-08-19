"""Chặng 1 — tài liệu gốc thành markdown.

    doc_parse.py     tài liệu -> markdown có heading, đã làm sạch   (<doc_id>.md)
      docx_parse.py    loader markitdown  — .docx
      pdf_parse.py     loader docling     — .pdf, cần extra `pdf`

Artifact DUY NHẤT là `.md`. Chặng này trả lời "tài liệu này VIẾT RA thành văn bản
gì", không trả lời "văn bản đó cấu tạo thế nào" — cắt block, đọc bảng, gán vai
trò đều thuộc `extract`.

Không ghi `DocumentIR` hay file metadata riêng. `doc_id`, `title`, `source_name`
và cảnh báo parse chỉ được truyền trong bộ nhớ sang `extract`.

Đây là chặng DUY NHẤT được phép biết quy ước của một bộ tài liệu cụ thể, vì nó là
chặng duy nhất phải biết .docx và .pdf hỏng theo hai kiểu khác nhau:

    DOCX   tên bảng dùng style `normal` nên ra bullet in đậm -> nâng lên `##`
    PDF    docling gán mọi tiêu đề level=1, nhưng số thứ tự còn ở `marker`
           -> SỐ quyết định cấp bậc; bảng bị ngắt trang thì nối lại

Luật phụ thuộc tài liệu nằm ở profile (`parse.table_heading`, `parse.replacements`),
không nằm trong code. Ra khỏi chặng này, mọi thứ phía sau chỉ còn biết CommonMark.

`doc_id` gồm cả đuôi nguồn (`..__docx`, `..__pdf`) vì mọi artifact đặt tên theo nó:
thiếu đuôi thì bản .docx và bản .pdf của cùng tài liệu ghi đè nhau, im lặng.

Chỉ nhận tài liệu tri thức. File testcase để chấm điểm không
đi qua đây, nó thuộc `eval/gold_parse.py`.
"""

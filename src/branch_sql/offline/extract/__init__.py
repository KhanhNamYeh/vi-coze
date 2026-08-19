"""Chặng 2 — markdown thành nội dung có cấu trúc.

    blocks.py          <doc_id>.md -> list[Block]   (trong bộ nhớ, không ghi file)
    block_extract.py   list[Block] -> <doc_id>.extract.json

Nhận `.md` — artifact duy nhất của `parse` — rồi làm hai việc:

    1. CẮT BLOCK bằng markdown-it, không bằng regex. Đây là luật của CommonMark
       nên nó thuộc về đây chứ không thuộc `parse`: `parse` biết .docx và .pdf
       hỏng ra sao, còn từ markdown trở đi thì hai định dạng là một.
    2. ĐỌC NỘI DUNG theo loại block: bảng thành `columns[]` + `rows[]`, văn bản
       cắt theo nhãn thành đoạn có `role`, heading giữ `level` và role.

Block KHÔNG được ghi ra file: nó là hàm thuần của (`.md`,
`extract.heading_roles`), nên
một `.blocks.json` chỉ là bản cache 40 KB cho một phép tính 40 ms, cộng một
schema nữa phải giữ đồng bộ với `.md`.

Không tạo `parent_id`, tổ tiên `section`/`table`, `caption_of` hay bất kỳ quan hệ
giữa element nào. Toàn bộ phần đó thuộc `link`.

Chạy bằng luật, không LLM. Mỗi phần tử mang `line_start`/`line_end` trỏ ngược về
dòng trong `.md` làm evidence — bất biến: cắt `.md` theo khoảng dòng đó phải ra
được đúng `text` của phần tử.

Quy ước của từng bộ tài liệu nằm ở profile (`extract.heading_roles`,
`extract.roles`), không nằm trong
code: nhãn "Mối liên kết:" là kiến thức của `config/sql.json`. Bộ tài liệu tiếng
Anh dùng `###` cho bảng chỉ cần đổi JSON.

Artifact có đúng envelope tối thiểu: `schema_version`, `doc_id`, `title`,
`source_name`, `warnings`, `elements`.
"""

"""Chặng `link` — gắn phần tử vào cây của tài liệu.

    hierarchy.py  <doc_id>.extract.json -> <doc_id>.linked.json

`extract` cho ra các element độc lập theo thứ tự đọc; chặng này gắn `parent_id`,
gắn tên tổ tiên theo vai trò heading (`section`, `table`, ...) và ghép nhãn đứng
riêng với nội dung ngay sau nó. Tất định, không LLM, không có khoá cấu hình.

Đây là mức tối thiểu mà pipeline RAG cần: chunk phải biết mình thuộc mục nào và
bảng nào. Diễn giải quan hệ nghiệp vụ - bảng nào nối bảng nào qua cột gì - thuộc
chặng `graph`, và nó không tất định như chặng này.
"""

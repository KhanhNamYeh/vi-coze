"""Chặng 2 — văn bản thành cấu trúc tường minh.

    merge_documents.py  gộp text + caption + metadata hình  [nhánh rag_docs]

CHƯA CÓ, cần bổ sung cho nhánh sql:

    schema_extract.py   markdown -> schema.json

Đây là nơi table / column / kiểu dữ liệu / khóa liên kết / business rule trở
thành trường dữ liệu thay vì câu tiếng Việt. Phải chạy bằng luật tường minh,
không dùng LLM, vì mỗi trường phải kèm được `evidence` là dòng gốc sinh ra nó.
"""

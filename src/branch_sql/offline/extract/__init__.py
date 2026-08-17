"""Chặng 2 — văn bản thành cấu trúc tường minh.

CHƯA CÓ, cần bổ sung:

    schema_extract.py   markdown -> schema.json

Đây là nơi table / column / kiểu dữ liệu / khóa liên kết / business rule trở
thành trường dữ liệu thay vì câu tiếng Việt. Phải chạy bằng luật tường minh,
không dùng LLM, vì mỗi trường phải kèm được `evidence` là dòng gốc sinh ra nó.

Chưa có chặng này nên `pipeline.py` đi thẳng từ parse sang chunk, và chặng
`link` phải đọc markdown bằng LLM thay vì đọc schema.json.
"""

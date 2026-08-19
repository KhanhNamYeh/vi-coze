"""Nhánh tài liệu mô tả schema CSDL (.docx).

    config.py   đường dẫn + tham số của nhánh, nạp từ `config/sql.json`
    offline/    raw -> parse -> extract -> link
    online/     query -> hybrid -> RRF -> rerank -> top-k chunk

    uv run python -m src.branch_sql.offline "Mô tả bảng BĐS (NEW).docx"
    uv run python -m src.branch_sql.online "câu hỏi"
"""

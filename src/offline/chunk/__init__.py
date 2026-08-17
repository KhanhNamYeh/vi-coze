"""Chặng 4 — cấu trúc thành chunk.

    table_chunker.py  1 bảng = 1 chunk, cắt theo heading  [nhánh sql]
    text_chunker.py   cắt theo token, có overlap          [nhánh rag_docs]

Hai nhánh phải xuất ra cùng một hợp đồng chunk (xem `src/schemas.py`), nếu không
tầng online phải biết chunk đến từ đâu.
"""

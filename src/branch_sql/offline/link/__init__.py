"""Chặng 3 — cấu trúc thành quan hệ.

    knowledge_graph.py  dựng graph node-link từ tài liệu

Bản hiện tại đọc thẳng markdown bằng LLM nên graph không có cạnh PK/FK nào và
không tái lập được. Hướng cần sửa: đọc schema.json của chặng 2, suy PK/FK bằng
luật, mỗi cạnh mang `basis` + `confidence` + `evidence`.
"""

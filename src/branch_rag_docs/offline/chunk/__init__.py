"""Chặng 4 — cấu trúc thành chunk.

    text_chunker.py  cắt theo token, có overlap

Văn bản trôi chảy không có ranh giới cấu trúc sẵn như bảng, nên phải có overlap
để câu bị cắt giữa chừng vẫn còn ngữ cảnh.

CẦN SỬA: metadata xuất ra còn là dict tự do, chưa theo hợp đồng `ChunkMeta` ở
`src/schemas.py` mà nhánh SQL đang dùng.
"""

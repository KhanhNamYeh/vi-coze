"""Các chặng của luồng offline. Mỗi thư mục con là một chặng, dùng chung cho mọi nhánh.

    parse    tài liệu gốc  -> văn bản có tọa độ
    extract  văn bản       -> cấu trúc (schema / outline)
    link     cấu trúc      -> quan hệ (PK/FK, business rule, tham chiếu)
    chunk    cấu trúc      -> chunk (render ra, không cắt lại văn bản)
    embed    chunk         -> vector dense + sparse
    index    vector        -> vector store
    verify   tất cả        -> đối soát ngược về tài liệu gốc

Thứ tự điều phối nằm ở `offline.py` của từng branch, không nằm ở đây.
"""

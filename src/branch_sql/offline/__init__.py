"""Các chặng offline của nhánh SQL. Mỗi thư mục con là một chặng.

    parse    .docx          -> markdown có heading
    extract  markdown       -> schema.json                    (CHƯA CÓ)
    link     markdown       -> knowledge graph                (cờ --kg)
    chunk    markdown       -> chunk, 1 bảng = 1 chunk
    embed    chunk          -> vector dense + BM25 thưa
    index    vector         -> Qdrant
    verify   tất cả         -> đối soát ngược về tài liệu gốc (CHƯA CÓ)

Thứ tự điều phối nằm ở `pipeline.py`, không nằm ở đây. Nhánh PDF có bộ chặng
riêng ở `src/branch_rag_docs/offline/`: cùng tên chặng, khác cách làm, nên
không dùng chung module.
"""

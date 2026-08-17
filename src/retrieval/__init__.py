"""Pipeline cho tài liệu mô tả schema CSDL.

    offline.py   .docx -> markdown -> chunk -> embed -> Qdrant
    online.py    query -> hybrid (dense + BM25) -> RRF -> rerank -> top-k chunk
    kg/          knowledge graph dựng từ markdown (nhánh prototype, chạy riêng)
"""

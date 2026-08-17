"""Các thành phần truy hồi của nhánh PDF, đối xứng với `offline/`.

    chroma_retriever.py  similarity search trên Chroma
    bge_reranker.py      cross-encoder bge

Thứ tự điều phối nằm ở `pipeline.py`. Không có nhánh BM25 nên không hybrid,
không RRF — yếu hơn nhánh SQL ở chỗ này.
"""

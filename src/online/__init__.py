"""Các thành phần của luồng online, đối xứng với `src/offline/`.

    qdrant_retriever.py  hybrid search dense + BM25       [nhánh sql]
    rerank.py            cross-encoder tiếng Việt         [nhánh sql]
    chroma_retriever.py  similarity search trên Chroma    [nhánh rag_docs]
    bge_reranker.py      cross-encoder bge                [nhánh rag_docs]
    kg_retriever.py      truy hồi trên knowledge graph    (prototype)

Thứ tự điều phối nằm ở `online.py` của từng branch.
"""

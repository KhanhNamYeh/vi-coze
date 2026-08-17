"""Các thành phần truy hồi của nhánh SQL, đối xứng với `offline/`.

    qdrant_retriever.py  hybrid search dense + BM25
    rerank.py            cross-encoder tiếng Việt
    kg_retriever.py      truy hồi trên knowledge graph (prototype)

Thứ tự điều phối nằm ở `pipeline.py`. Vector hoá query đi qua
`offline/embed/` để index và query không lệch model.
"""

"""Pipeline cho tài liệu PDF.

    pdf_loader.py -> chunker.py -> indexer.py (Chroma) -> retriever.py -> reranker.py

Tách khỏi nhánh SQL: khác vector store (Chroma), khác model (bge-m3).
"""

"""Nhánh tài liệu văn bản (.pdf).

    config.py   đường dẫn + tham số của nhánh, nạp từ `config/rag_docs.json`
    offline/    parse -> [extract] -> chunk -> embed + index
    online/     query -> similarity search -> rerank -> top-k chunk

    uv sync --extra rag_docs
    uv run python -m src.branch_rag_docs.offline "[Reading]-RAG-System.pdf"
    uv run python -m src.branch_rag_docs.online "câu hỏi"
"""

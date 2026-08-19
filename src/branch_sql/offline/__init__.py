"""Các chặng offline của nhánh SQL. Mỗi thư mục con là một chặng.

    parse    PDF/DOCX/XLSX  -> canonical Markdown
    extract  Markdown       -> independent structured elements
    link     elements       -> parent-child + tên tổ tiên
    chunk    elements       -> chunk + metadata
    embed    chunk          -> chunk_id + dense vector
    index    chunk + vector -> Qdrant (dense + BM25)
    verify   đối soát và chấm điểm, đứng ngoài chuỗi
    graph    knowledge graph, có gọi LLM  (prototype, ngoài pipeline)

Thứ tự điều phối nằm ở `project.py`, chạy theo DỰ ÁN chứ không theo file: bộ
tri thức nào thuộc dự án nào khai ở `knowledge[]` trong profile. Sáu chặng đầu
tất định; `graph` gọi LLM nên đứng riêng.
"""

"""Các chặng offline của nhánh SQL. Mỗi thư mục con là một chặng.

    parse    PDF/DOCX       -> canonical Markdown
    extract  Markdown       -> independent structured elements
    link     elements       -> parent-child + tên tổ tiên
    graph    knowledge graph, có gọi LLM  (prototype, ngoài pipeline)

Thứ tự điều phối nằm ở `pipeline.py`: raw -> parse -> extract -> link. Ba chặng
đó tất định; `graph` gọi LLM nên đứng riêng, không nằm trong chain.
"""

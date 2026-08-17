"""vi-coze — pipeline RAG tiếng Việt.

Mỗi bộ tài liệu là một "nhánh", đặt tên theo hậu tố:

    config_sql.py / offline_sql.py / online_sql.py   nhánh tài liệu schema CSDL
    src/retrieval/                                    các bước dùng chung
    src/pdf/                                          nhánh tài liệu PDF (chưa có entry point)
"""

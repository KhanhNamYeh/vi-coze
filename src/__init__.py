"""vi-coze — pipeline RAG tiếng Việt.

    src/offline/           các chặng xử lý offline, dùng chung
    src/online/            các thành phần truy hồi, dùng chung
    src/branch_sql/        nhánh tài liệu schema CSDL   — offline / online / config
    src/branch_rag_docs/   nhánh tài liệu PDF           — offline / online / config
    src/schemas.py         hợp đồng chunk chung cho mọi nhánh
"""

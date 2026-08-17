"""vi-coze — pipeline RAG tiếng Việt.

    src/branch_sql/        nhánh tài liệu schema CSDL (.docx)
    src/branch_rag_docs/   nhánh tài liệu PDF
    src/config.py          đọc profile JSON trong `config/`
    src/schemas.py         hợp đồng chunk chung cho mọi nhánh

Mỗi nhánh tự chứa cả hai luồng, không dùng chung module xử lý:

    <nhánh>/config.py    đường dẫn + tham số, nạp từ profile
    <nhánh>/offline/     các chặng dựng index  — pipeline.py điều phối
    <nhánh>/online/      các bước truy hồi     — pipeline.py điều phối

Hai nhánh cùng tên chặng nhưng khác cách làm (docx/heading so với pdf/số trang,
Qdrant hybrid so với Chroma dense), nên tách hẳn: sửa một nhánh không đụng nhánh
kia. Chỗ thật sự dùng chung chỉ còn `config.py` và `schemas.py`.
"""

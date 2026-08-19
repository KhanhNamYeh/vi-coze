"""Chặng `index` — chunk + vector vào hệ thống tìm kiếm.

    qdrant_store.py  -> Qdrant, cần `docker compose up -d`

Một collection, HAI đường tìm kiếm trên cùng tập point: named vector `dense`
(cosine) cho ngữ nghĩa, và named sparse vector `bm25` cho từ khoá chính xác.
Chung point nên hai chỉ mục không thể lệch tập tài liệu.

`Modifier.IDF` bắt buộc với sparse vector của FastEmbed - thiếu nó thì điểm BM25
sai công thức mà không có lỗi nào báo.
"""

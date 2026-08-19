"""Chặng `verify` — index đã dùng được chưa.

    integrity.py  đối soát chunk <-> vector <-> point trong Qdrant
    retrieval.py  đo và chỉnh tham số truy hồi trên tập dev

`integrity` trả lời "có mất mát hay hỏng hóc gì không": trùng chunk_id, chunk
rỗng, vượt budget, lệch số lượng, sai chiều, NaN, point thiếu một trong hai
vector, mất page_content hay metadata. Mã thoát khác 0 khi có lỗi.

`retrieval` trả lời "truy hồi tốt tới đâu, và tham số nào là tốt nhất". Dev chỉ
để CHỌN tham số; số đưa vào báo cáo phải đo trên `test.json`.
"""

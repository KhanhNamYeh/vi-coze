"""Các chặng offline của nhánh PDF. Mỗi thư mục con là một chặng.

    parse    .pdf           -> block có page/bbox, + tách hình và caption
    extract  block + caption -> tài liệu đã gộp theo trang        (cờ --images)
    link     —                                                    (CHƯA CÓ)
    chunk    tài liệu       -> chunk cắt theo token, có overlap
    index    chunk          -> Chroma (embed nằm trong chặng này)
    verify   chunk          -> thống kê phân bố, chạy tay

Thứ tự điều phối nằm ở `pipeline.py`, không nằm ở đây. Nhánh SQL có bộ chặng
riêng ở `src/branch_sql/offline/`: cùng tên chặng, khác cách làm, nên không
dùng chung module.
"""

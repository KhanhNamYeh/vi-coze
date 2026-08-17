"""Chặng 1 — tài liệu gốc thành văn bản có tọa độ.

    pdf_parse.py        .pdf -> block có page/bbox   (docling)
    image_extractor.py  tách hình khỏi pdf           (cờ --images)
    image_captioner.py  sinh caption cho hình        (cờ --images, model BLIP)

Ra khỏi chặng này, mỗi đơn vị văn bản phải nhớ được nó đến từ đâu trong file
gốc: ở nhánh này tọa độ là số trang.
"""

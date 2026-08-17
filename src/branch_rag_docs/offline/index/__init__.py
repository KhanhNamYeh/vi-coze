"""Chặng 5 — chunk thành vector rồi vào store.

    chroma_store.py  embed dense -> Chroma trên đĩa, không cần server

Khác nhánh SQL: embedding không tách thành chặng riêng mà nằm luôn trong
`build_index`, và không có nhánh sparse nào.
"""

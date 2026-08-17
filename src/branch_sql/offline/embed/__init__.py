"""Chặng 5a — chunk thành vector.

    dense.py        embedding dense, dùng chung index và query
    sparse.py       BM25 thưa, dùng chung index và query
    kg_embedder.py  embed từng triple của knowledge graph (prototype)

Index và query phải đi qua cùng module: lệch model hay lệch normalize không ném
lỗi, chỉ làm điểm truy hồi kém. Vì vậy `src/branch_sql/online/` import thẳng
hai file này thay vì tự nạp model.
"""

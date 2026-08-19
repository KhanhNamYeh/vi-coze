"""Chặng `embed` — chunk thành vector.

    encoder.py      <doc_id>.chunks.jsonl -> <doc_id>.vectors.npz   (chunk_id -> vector)
    dense.py        model + tokenizer, dùng chung index và query
    sparse.py       BM25 thưa, dùng chung index và query
    kg_embedder.py  embed từng triple của knowledge graph (prototype)

Index và query phải đi qua cùng module: lệch model hay lệch normalize không ném
lỗi, chỉ làm điểm truy hồi kém. Vì vậy `src/branch_sql/online/` import thẳng
`dense.py` và `sparse.py` thay vì tự nạp model.

Artifact tách riêng khỏi chặng `index` vì embed là phần đắt nhất của pipeline
còn upsert thì rẻ: đổi vector store không phải embed lại, và `verify` soi được
vector trước khi chúng vào store.
"""

import json
import torch
import numpy as np
from pathlib import Path
from sentence_transformers import SentenceTransformer


def create_kb_embeddings(kb_path="final_sql_kb.json", output_path="kb_index.npz"):
    # 1. Cấu hình Model & GPU
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"--- Loading BGE-M3 on {device} ---")
    model = SentenceTransformer("BAAI/bge-m3", device=device)

    # 2. Đọc dữ liệu tri thức
    with open(kb_path, "r", encoding="utf-8") as f:
        kb_data = json.load(f)

    triples = kb_data.get('edges', [])
    if not triples:
        print("(!) Không có dữ liệu trong KG.")
        return

    # 3. Tạo văn bản để tìm kiếm (Kết hợp Subject và Quan hệ)
    # Ví dụ: "sinh trước năm 1950 mapping"
    documents = [f"{t['source']} {t['label']}" for t in triples]

    print(f"--- Đang encode {len(documents)} triples... ---")
    embeddings = model.encode(
        documents,
        normalize_embeddings=True,
        show_progress_bar=True,
        batch_size=32
    )

    # 4. Lưu lại Index
    # Lưu cả embeddings và documents để sql_retrieval.py không cần đọc lại JSON quá nhiều
    np.savez(
        output_path,
        embeddings=embeddings,
        documents=np.array(documents, dtype=object),
        targets=np.array([t['target'] for t in triples], dtype=object),
        sources=np.array([t['source'] for t in triples], dtype=object)
    )
    print(f"--- Đã xuất file chỉ mục: {output_path} ---")


if __name__ == "__main__":
    # Lấy đường dẫn tuyệt đối đến thư mục chứa file embedder.py hiện tại
    current_dir = Path(__file__).parent

    # Trỏ vào file JSON nằm trong thư mục processing
    kb_file = current_dir / "processing" / "final_sql_kb.json"
    output_index = current_dir / "kb_index.npz"

    print(f"Đang tìm file: {kb_file}")

    create_kb_embeddings(
        kb_path=str(kb_file),
        output_path=str(output_index)
    )
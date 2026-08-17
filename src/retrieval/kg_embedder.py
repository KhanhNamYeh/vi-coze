import json
import torch
import numpy as np
from pathlib import Path
from sentence_transformers import SentenceTransformer

from ..config_sql import KG_INDEX, KNOWLEDGE_DIR


def create_kb_embeddings(kb_path, output_path):
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"--- Loading BGE-M3 on {device} ---")
    model = SentenceTransformer("BAAI/bge-m3", device=device)

    with open(kb_path, "r", encoding="utf-8") as f:
        kb_data = json.load(f)

    node_info = {}
    for n in kb_data['nodes']:
        node_id = n.get('id')
        # Thử lấy title, nếu không có lấy label, nếu không có nữa lấy chính id
        display_text = n.get('title') or n.get('label') or node_id
        node_info[node_id] = str(display_text).strip()

    triples = kb_data.get('edges', [])
    documents = []
    sources = []
    targets = []
    labels = []

    print(f"--- Đang chuẩn bị dữ liệu cho {len(triples)} quan hệ... ---")

    for t in triples:
        src_id = t['source']
        tgt_id = t['target']
        edge_label = t['label']

        src_context = node_info.get(src_id, src_id)
        tgt_context = node_info.get(tgt_id, tgt_id)

        combined_text = f"{src_context} {edge_label} {tgt_context}"
        clean_text = " ".join(combined_text.split())

        documents.append(clean_text)
        sources.append(src_id)
        targets.append(tgt_id)
        labels.append(edge_label)

    print(f"--- Đang encode {len(documents)} triples... ---")
    embeddings = model.encode(
        documents,
        normalize_embeddings=True,
        show_progress_bar=True,
        batch_size=32
    )

    np.savez(
        output_path,
        embeddings=embeddings,
        documents=np.array(documents, dtype=object),
        targets=np.array(targets, dtype=object),
        sources=np.array(sources, dtype=object),
        labels=np.array(labels, dtype=object)
    )
    print(f"--- Đã xuất file chỉ mục: {output_path} ---")


if __name__ == "__main__":
    kb_file = KNOWLEDGE_DIR / "sql_knowledge_map1.json"
    output_index = KG_INDEX
    output_index.parent.mkdir(parents=True, exist_ok=True)

    print(f"Đang tìm file: {kb_file}")

    if not kb_file.exists():
        print(f"(!) Lỗi: Không tìm thấy file tại {kb_file}")
    else:
        create_kb_embeddings(
            kb_path=str(kb_file),
            output_path=str(output_index)
        )
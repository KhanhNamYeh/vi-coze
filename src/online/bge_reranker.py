"""
Module tái xếp hạng ngữ nghĩa bằng Cross-Encoder (BAAI/bge-reranker-v2-m3).
"""
import math
import os
from pathlib import Path
from typing import Any

# Tự động trỏ cache HuggingFace sang ổ D (nếu có) để tránh đầy ổ C
if "HF_HOME" not in os.environ and Path("D:/").exists():
    os.environ["HF_HOME"] = "D:/hf_cache"

import torch
from sentence_transformers import CrossEncoder


class LegalReranker:
    """Tái xếp hạng danh sách tài liệu ứng viên dựa trên điểm liên quan ngữ nghĩa chính xác."""

    def __init__(
        self,
        model_name: str = "BAAI/bge-reranker-v2-m3",
        max_length: int = 512,
    ):
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        print(f"[Reranker] Đang nạp mô hình '{model_name}' trên {self.device.upper()}...")

        self.model = CrossEncoder(
            model_name,
            max_length=max_length,
            device=self.device
        )
        print("[Reranker] Sẵn sàng phục vụ tái xếp hạng.")

    def rerank(
        self,
        query: str,
        candidates: list[dict[str, Any]],
        top_k: int = 5
    ) -> list[dict[str, Any]]:
        """Chấm điểm cặp (query, candidate document) và sắp xếp lại theo độ liên quan giảm dần."""
        if not candidates:
            return []

        # Tạo danh sách các cặp [query, doc_text]
        pairs = [[query, item["document"].page_content] for item in candidates]

        # Tính raw logits
        raw_scores = self.model.predict(pairs, show_progress_bar=False)

        # Chuyển raw logits sang xác suất chuẩn hóa qua hàm Sigmoid [0, 1]
        reranked_results = []
        for item, score in zip(candidates, raw_scores):
            prob = 1.0 / (1.0 + math.exp(-float(score)))
            reranked_results.append({
                "document": item["document"],
                "vector_distance": item["vector_distance"],
                "reranker_score": prob
            })

        # Sắp xếp điểm cao nhất lên đầu
        reranked_results.sort(key=lambda x: x["reranker_score"], reverse=True)
        return reranked_results[:top_k]

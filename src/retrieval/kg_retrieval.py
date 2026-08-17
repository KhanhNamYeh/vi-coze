import numpy as np
import torch
import json
import re
from pathlib import Path
from rank_bm25 import BM25Okapi
from sentence_transformers import SentenceTransformer, CrossEncoder

from ..config_sql import KG_INDEX


class SQLRetriever:
    def __init__(self, index_path=KG_INDEX, k=5):
        self.k = k
        self.device = "cuda" if torch.cuda.is_available() else "cpu"

        print(f"--- Loading Index from {index_path} ---")
        if not Path(index_path).exists():
            raise FileNotFoundError(f"Index file {index_path} not found. Run embedder.py first.")

        data = np.load(index_path, allow_pickle=True)

        self.kb_embeddings = data['embeddings']
        self.documents = data['documents'].tolist()
        self.targets = data['targets'].tolist()
        self.sources = data['sources'].tolist()

        print(f"--- Loading Models to {self.device} ---")
        self.embed_model = SentenceTransformer("BAAI/bge-m3", device=self.device)
        self.rerank_model = CrossEncoder("BAAI/bge-reranker-v2-m3", device=self.device)

        print("--- Initializing BM25 ---")
        tokenized_corpus = [doc.lower().split() for doc in self.documents]
        self.bm25 = BM25Okapi(tokenized_corpus)

    def hybrid_search(self, query):
        query_lower = query.lower()

        bm25_scores = self.bm25.get_scores(query_lower.split())

        query_emb = self.embed_model.encode(query_lower, normalize_embeddings=True, show_progress_bar=False)
        vector_scores = np.dot(self.kb_embeddings, query_emb)

        def get_ranks(scores):
            return np.argsort(np.argsort(-scores))

        bm_ranks = get_ranks(bm25_scores)
        vec_ranks = get_ranks(vector_scores)

        rrf_scores = (1.0 / (bm_ranks + 60)) + (1.0 / (vec_ranks + 60))

        top_indices = np.argsort(-rrf_scores)[:20]
        candidates = [self.documents[i] for i in top_indices]

        pairs = [[query, cand] for cand in candidates]
        rerank_scores = self.rerank_model.predict(pairs)

        final_list = []
        for i, score in enumerate(rerank_scores):
            idx = top_indices[i]
            final_list.append({
                "source": self.sources[idx],
                "target": self.targets[idx],
                "rerank_score": float(score),
                "content": candidates[i]
            })

        return sorted(final_list, key=lambda x: x['rerank_score'], reverse=True)[:self.k]


if __name__ == "__main__":
    try:
        retriever = SQLRetriever(index_path=str(KG_INDEX))
        test_queries = [
            "Tìm các điểm bán ở phường Vũng Tàu và nhân viên chăm sóc",
            "Doanh thu Saymee hôm nay",
            "Thống kê thuê bao phát triển mới tháng này theo cửa hàng",
            "Trạm BTS nào đang hoạt động và có VLR cao nhất?"
        ]

        for q in test_queries:
            print(f"\n[QUERY]: {q}")
            results = retriever.hybrid_search(q)
            for i, res in enumerate(results):
                print(f"  {i + 1}. [{res['rerank_score']:>6.2f}] {res['source']} -> {res['target']}")

    except Exception as e:
        print(f"Error: {e}")
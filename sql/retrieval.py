import numpy as np
import torch
import json
import re
from pathlib import Path  # Fixed: Added missing import
from rank_bm25 import BM25Okapi
from sentence_transformers import SentenceTransformer, CrossEncoder


class SQLRetriever:
    def __init__(self, index_path="kb_index.npz", k=5):
        self.k = k
        self.device = "cuda" if torch.cuda.is_available() else "cpu"

        # 1. Load the Index File
        # This file contains both the Vectors AND the Natural Language text
        print(f"--- Loading Index from {index_path} ---")
        if not Path(index_path).exists():
            raise FileNotFoundError(f"Index file {index_path} not found. Run embedder.py first.")

        data = np.load(index_path, allow_pickle=True)

        self.kb_embeddings = data['embeddings']
        # These are the strings used for BM25 (e.g., "sinh trước năm 1950 mapping")
        self.documents = data['documents'].tolist()
        self.targets = data['targets'].tolist()
        self.sources = data['sources'].tolist()

        # 2. Load Models
        print(f"--- Loading Models to {self.device} ---")
        self.embed_model = SentenceTransformer("BAAI/bge-m3", device=self.device)
        self.rerank_model = CrossEncoder("BAAI/bge-reranker-v2-m3", device=self.device)

        # 3. Build BM25 Index using the text stored inside the .npz
        print("--- Initializing BM25 ---")
        tokenized_corpus = [doc.lower().split() for doc in self.documents]
        self.bm25 = BM25Okapi(tokenized_corpus)

    def hybrid_search(self, query):
        query_lower = query.lower()

        # --- A. BM25 Scoring (Keyword Matching) ---
        bm25_scores = self.bm25.get_scores(query_lower.split())

        # --- B. Vector Scoring (Semantic Matching) ---
        query_emb = self.embed_model.encode(query_lower, normalize_embeddings=True, show_progress_bar=False)
        vector_scores = np.dot(self.kb_embeddings, query_emb)

        # --- C. Reciprocal Rank Fusion (RRF) ---
        def get_ranks(scores):
            return np.argsort(np.argsort(-scores))

        bm_ranks = get_ranks(bm25_scores)
        vec_ranks = get_ranks(vector_scores)

        # RRF formula balances keyword and semantic strengths
        rrf_scores = (1.0 / (bm_ranks + 60)) + (1.0 / (vec_ranks + 60))

        # Get Top 20 candidates for the final Reranker stage
        top_indices = np.argsort(-rrf_scores)[:20]
        candidates = [self.documents[i] for i in top_indices]

        # --- D. Cross-Encoder Reranking (High Precision) ---
        # The reranker looks at the Query and Candidate together
        pairs = [[query, cand] for cand in candidates]
        rerank_scores = self.rerank_model.predict(pairs)

        # --- E. Final Sorting ---
        final_list = []
        for i, score in enumerate(rerank_scores):
            idx = top_indices[i]
            final_list.append({
                "source": self.sources[idx],
                "target": self.targets[idx],
                "rerank_score": float(score)
            })

        # Sort by reranker score and return top-k
        return sorted(final_list, key=lambda x: x['rerank_score'], reverse=True)[:self.k]


if __name__ == "__main__":
    # Ensure we use the correct path relative to this script
    current_dir = Path(__file__).parent
    index_file = current_dir / "kb_index.npz"

    try:
        retriever = SQLRetriever(index_path=str(index_file))

        test_queries = [
            "Liệt kê các quận có khách hàng sinh trước năm 1950",
            "Có bao nhiêu khách hàng dùng đồng koruna của séc?",
            "khách hàng 6 tiêu thụ bao nhiêu"
        ]

        for q in test_queries:
            print(f"\n[QUERY]: {q}")
            results = retriever.hybrid_search(q)
            for i, res in enumerate(results):
                # Higher score (> 0) means high relevance
                print(f"  {i + 1}. [{res['rerank_score']:>6.2f}] {res['source']} -> {res['target']}")

    except Exception as e:
        print(f"Error: {e}")
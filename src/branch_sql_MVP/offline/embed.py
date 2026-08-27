"""Tạo dense và BM25 sparse vector cho child chunks."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from ..settings import EmbeddingSettings, Settings, load_settings
from . import graph
from .chunk import load_chunks


@lru_cache(maxsize=4)
def _dense(model: str, device: str):
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(model, device=device)


@lru_cache(maxsize=4)
def _sparse(model: str, k: float, b: float, disable_stemmer: bool):
    from fastembed import SparseTextEmbedding

    return SparseTextEmbedding(model_name=model, k=k, b=b, disable_stemmer=disable_stemmer)


def dense_passages(texts: list[str], cfg: EmbeddingSettings) -> list[list[float]]:
    vectors = _dense(cfg.dense_model, cfg.device).encode(
        texts,
        batch_size=cfg.batch_size,
        normalize_embeddings=cfg.normalize,
        convert_to_numpy=True,
        show_progress_bar=False,
    )
    return vectors.astype("float32").tolist()


def dense_query(text: str, cfg: EmbeddingSettings) -> list[float]:
    return dense_passages([text], cfg)[0]


def sparse_passages(texts: list[str], cfg: EmbeddingSettings) -> list[dict]:
    values = _sparse(cfg.sparse_model, cfg.bm25_k, cfg.bm25_b, cfg.disable_stemmer).embed(texts)
    return [{"indices": item.indices.tolist(), "values": item.values.tolist()} for item in values]


def sparse_query(text: str, cfg: EmbeddingSettings) -> dict:
    model = _sparse(cfg.sparse_model, cfg.bm25_k, cfg.bm25_b, cfg.disable_stemmer)
    item = next(iter(model.query_embed(text)))
    return {"indices": item.indices.tolist(), "values": item.values.tolist()}


def encode(chunks: list[dict], cfg: EmbeddingSettings) -> list[dict]:
    if not chunks:
        raise ValueError("embed nhận 0 chunk")
    texts = [chunk["text"] for chunk in chunks]
    dense = dense_passages(texts, cfg)
    sparse = sparse_passages(texts, cfg)
    if len(dense) != len(chunks) or len(sparse) != len(chunks):
        raise ValueError("số vector trả về không khớp số chunk")
    dimension = len(dense[0])
    if not dimension or any(len(vector) != dimension for vector in dense):
        raise ValueError("dense model trả vector rỗng hoặc sai chiều")
    return [
        {"id": chunk["id"], "dense": dv, "sparse": sv}
        for chunk, dv, sv in zip(chunks, dense, sparse)
    ]


def run(doc_id: str, *, settings: Settings | None = None) -> dict:
    app = settings or load_settings()
    vectors = encode(load_chunks(doc_id, settings=app), app.embedding)
    output = app.path(app.paths.artifacts) / f"{doc_id}.vectors.jsonl"
    output.write_text("".join(json.dumps(row) + "\n" for row in vectors), encoding="utf-8")
    graph_vectors: list[dict] = []
    graph_output = app.path(app.paths.artifacts) / f"{doc_id}.graph_vectors.jsonl"
    graph_artifact = app.path(app.paths.artifacts) / f"{doc_id}.graph.json"
    if app.graph.enabled and graph_artifact.exists():
        graph_items = graph.embedding_items(doc_id, settings=app)
        encoded = encode(graph_items, app.embedding) if graph_items else []
        graph_vectors = [
            {**vector, "kind": item["kind"]}
            for item, vector in zip(graph_items, encoded)
        ]
        graph_output.write_text(
            "".join(json.dumps(row) + "\n" for row in graph_vectors),
            encoding="utf-8",
        )
    return {
        "doc_id": doc_id,
        "vectors": len(vectors),
        "graph_vectors": len(graph_vectors),
        "dimension": len(vectors[0]["dense"]),
        "path": str(output),
        "graph_path": str(graph_output) if graph_vectors else None,
    }


def load_vectors(doc_id: str, *, settings: Settings | None = None) -> list[dict]:
    app = settings or load_settings()
    path = app.path(app.paths.artifacts) / f"{doc_id}.vectors.jsonl"
    if not path.exists():
        raise FileNotFoundError(f"chưa có {path.name}; chạy embed trước")
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not rows:
        raise ValueError(f"{path.name} không có vector")
    return rows


def load_graph_vectors(doc_id: str, *, settings: Settings | None = None) -> list[dict]:
    app = settings or load_settings()
    path = app.path(app.paths.artifacts) / f"{doc_id}.graph_vectors.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]

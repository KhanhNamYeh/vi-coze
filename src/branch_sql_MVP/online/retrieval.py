"""Semantic, keyword hoặc hybrid retrieval; hybrid luôn rerank."""

from __future__ import annotations

from collections import defaultdict
from functools import lru_cache

from ..offline.embed import dense_query, sparse_query
from ..offline.index import client
from ..settings import Settings, load_settings


def _family(model: str) -> str:
    return model.split("/", 1)[0].lower() if "/" in model else model.split("-", 1)[0].lower()


def ensure_same_family(settings: Settings) -> None:
    dense = settings.embedding.dense_model
    rerank = settings.embedding.rerank_model
    if _family(dense) != _family(rerank):
        raise ValueError(f"dense '{dense}' và reranker '{rerank}' không cùng họ model")


@lru_cache(maxsize=4)
def _reranker(model: str, device: str):
    from sentence_transformers import CrossEncoder

    return CrossEncoder(model, device=device)


def _hit(point, score: float | None = None) -> dict:
    payload = dict(point.payload or {})
    text = payload.get("parent_text") or payload.get("text", "")
    return {"score": float(point.score if score is None else score), "text": text, "metadata": payload}


def _dedupe(hits: list[dict]) -> list[dict]:
    output: list[dict] = []
    seen: set[str] = set()
    for hit in hits:
        metadata = hit["metadata"]
        key = (
            metadata.get("parent_id")
            or metadata.get("parent_chunk_id")
            or metadata.get("id")
            or metadata.get("chunk_id")
        )
        if key in seen:
            continue
        seen.add(key)
        output.append(hit)
    return output


def retrieve(
    query: str,
    *,
    kind: str,
    knowledge_id: str | None = None,
    exclude_section_ids: set[str] | None = None,
    settings: Settings | None = None,
) -> list[dict]:
    from qdrant_client import models

    app = settings or load_settings()
    cfg = app.retrieval
    selected_knowledge = knowledge_id or app.index.knowledge_id
    collection = app.index.collection(selected_knowledge, kind)
    qdrant = client(app)
    if not qdrant.collection_exists(collection):
        if kind == "graph":
            return []
        raise ValueError(
            f"knowledge_id '{selected_knowledge}' chưa có collection '{collection}'; "
            "hãy index dữ liệu trước"
        )
    final_k = {
        "docs": cfg.docs_top_k,
        "sql": cfg.sql_top_k,
        "graph": cfg.graph_top_k,
    }[kind]

    def semantic(limit: int):
        return qdrant.query_points(
            collection,
            query=dense_query(query, app.embedding),
            using=app.index.dense_vector,
            limit=limit,
            with_payload=True,
        ).points

    def keyword(limit: int):
        vector = sparse_query(query, app.embedding)
        return qdrant.query_points(
            collection,
            query=models.SparseVector(**vector),
            using=app.index.sparse_vector,
            limit=limit,
            with_payload=True,
        ).points

    if cfg.mode == "semantic":
        hits = [_hit(point) for point in semantic(cfg.candidate_k)]
    elif cfg.mode == "keyword":
        hits = [_hit(point) for point in keyword(cfg.candidate_k)]
    else:
        ensure_same_family(app)
        scores: dict[str, float] = defaultdict(float)
        points: dict[str, object] = {}
        for weight, ranked in (
            (cfg.semantic_weight, semantic(cfg.candidate_k)),
            (cfg.keyword_weight, keyword(cfg.candidate_k)),
        ):
            for rank, point in enumerate(ranked, 1):
                key = str(point.id)
                scores[key] += weight / (cfg.rrf_k + rank)
                points.setdefault(key, point)
        fused = sorted(scores, key=scores.get, reverse=True)[: cfg.rerank_top_k]
        # Rerank child text đã được chunk thay vì parent_text có thể rất dài.
        pairs = [(query, (points[key].payload or {}).get("text", "")) for key in fused]
        rerank_scores = _reranker(app.embedding.rerank_model, app.embedding.device).predict(pairs) if pairs else []
        hits = sorted(
            [_hit(points[key], float(score)) for key, score in zip(fused, rerank_scores)],
            key=lambda item: item["score"],
            reverse=True,
        )

    if exclude_section_ids:
        excluded = {str(value).strip().casefold() for value in exclude_section_ids}
        hits = [
            hit
            for hit in hits
            if str(hit["metadata"].get("section_id", "")).strip().casefold() not in excluded
        ]
    hits = _dedupe(hits)
    if cfg.min_score is not None:
        hits = [hit for hit in hits if hit["score"] >= cfg.min_score]
    for hit in hits:
        hit["metadata"].setdefault("knowledge_id", selected_knowledge)
    return hits[:final_k]


def retrieve_both(
    query: str,
    *,
    knowledge_id: str | None = None,
    settings: Settings | None = None,
) -> dict[str, list[dict]]:
    app = settings or load_settings()
    return {
        "docs": retrieve(query, kind="docs", knowledge_id=knowledge_id, settings=app),
        "sql": retrieve(query, kind="sql", knowledge_id=knowledge_id, settings=app),
        "graph": retrieve(query, kind="graph", knowledge_id=knowledge_id, settings=app) if app.graph.enabled else [],
    }

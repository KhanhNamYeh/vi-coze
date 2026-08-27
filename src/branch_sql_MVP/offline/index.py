"""Upsert child chunks cùng dense/sparse vector vào Qdrant."""

from __future__ import annotations

import atexit
import json
import os
import uuid
from functools import lru_cache

from ..settings import Settings, load_settings
from . import graph
from .chunk import load_chunks
from .embed import load_graph_vectors, load_vectors

NAMESPACE = uuid.UUID("d8ac352c-5207-4e68-b968-e12034db6703")
_CLIENTS = []


def _close_clients() -> None:
    for qdrant in _CLIENTS:
        qdrant.close()


atexit.register(_close_clients)


@lru_cache(maxsize=4)
def _client(url: str, api_key: str | None, local_path: str | None):
    from qdrant_client import QdrantClient

    qdrant = QdrantClient(path=local_path) if local_path else QdrantClient(url=url, api_key=api_key)
    _CLIENTS.append(qdrant)
    return qdrant


def client(settings: Settings):
    key = os.getenv(settings.index.api_key_env) if settings.index.api_key_env else None
    local_path = str(settings.path(settings.index.local_path)) if settings.index.local_path else None
    return _client(settings.index.url, key, local_path)


def ensure_collection(qdrant, name: str, dimension: int, settings: Settings, recreate: bool) -> bool:
    from qdrant_client import models

    if recreate and qdrant.collection_exists(name):
        qdrant.delete_collection(name)
    if qdrant.collection_exists(name):
        info = qdrant.get_collection(name)
        vectors = info.config.params.vectors or {}
        current = vectors.get(settings.index.dense_vector)
        if current is None or current.size != dimension:
            raise ValueError(f"collection '{name}' không khớp dense vector {dimension} chiều")
        return False
    qdrant.create_collection(
        collection_name=name,
        vectors_config={settings.index.dense_vector: models.VectorParams(size=dimension, distance=models.Distance.COSINE)},
        sparse_vectors_config={settings.index.sparse_vector: models.SparseVectorParams(modifier=models.Modifier.IDF)},
    )
    return True


def _parents(doc_id: str, settings: Settings) -> dict[str, str]:
    path = settings.path(settings.paths.artifacts) / f"{doc_id}.parents.jsonl"
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return {row["id"]: row["text"] for row in rows}


def run(
    doc_id: str,
    *,
    kind: str,
    knowledge_id: str | None = None,
    recreate: bool | None = None,
    settings: Settings | None = None,
) -> dict:
    from qdrant_client import models

    app = settings or load_settings()
    selected_knowledge = knowledge_id or app.index.knowledge_id
    chunks = load_chunks(doc_id, settings=app)
    vectors = {row["id"]: row for row in load_vectors(doc_id, settings=app)}
    if {row["id"] for row in chunks} != set(vectors):
        raise ValueError("chunk và vector không cùng tập id; chạy lại embed")
    parents = _parents(doc_id, app)
    dimension = len(next(iter(vectors.values()))["dense"])
    collection = app.index.collection(selected_knowledge, kind)
    qdrant = client(app)
    created = ensure_collection(qdrant, collection, dimension, app, app.index.recreate if recreate is None else recreate)

    points = []
    for chunk in chunks:
        vector = vectors[chunk["id"]]
        points.append(models.PointStruct(
            id=str(uuid.uuid5(NAMESPACE, chunk["id"])),
            vector={
                app.index.dense_vector: vector["dense"],
                app.index.sparse_vector: models.SparseVector(**vector["sparse"]),
            },
            payload={
                **chunk,
                "doc_id": doc_id,
                "kind": kind,
                "knowledge_id": selected_knowledge,
                "parent_text": parents.get(chunk["parent_id"], ""),
            },
        ))
    for start in range(0, len(points), app.index.batch_size):
        qdrant.upsert(collection, points=points[start : start + app.index.batch_size], wait=True)

    graph_points = []
    graph_collection = None
    if app.graph.enabled and kind in app.graph.source_kinds:
        graph_vectors = {row["id"]: row for row in load_graph_vectors(doc_id, settings=app)}
        if graph_vectors:
            graph_items = {row["id"]: row for row in graph.embedding_items(doc_id, settings=app)}
            if set(graph_items) != set(graph_vectors):
                raise ValueError("graph artifact và graph vector không cùng tập id; chạy lại graph rồi embed")
            graph_collection = app.index.collection(selected_knowledge, "graph")
            ensure_collection(
                qdrant,
                graph_collection,
                dimension,
                app,
                app.index.recreate if recreate is None else recreate,
            )
            for item_id, item in graph_items.items():
                vector = graph_vectors[item_id]
                graph_points.append(models.PointStruct(
                    id=str(uuid.uuid5(NAMESPACE, f"graph:{doc_id}:{item_id}")),
                    vector={
                        app.index.dense_vector: vector["dense"],
                        app.index.sparse_vector: models.SparseVector(**vector["sparse"]),
                    },
                    payload={
                        **item["metadata"],
                        "id": item_id,
                        "text": item["text"],
                        "kind": item["kind"],
                        "doc_id": doc_id,
                        "knowledge_id": selected_knowledge,
                    },
                ))
            for start in range(0, len(graph_points), app.index.batch_size):
                qdrant.upsert(
                    graph_collection,
                    points=graph_points[start : start + app.index.batch_size],
                    wait=True,
                )
    return {
        "doc_id": doc_id,
        "knowledge_id": selected_knowledge,
        "collection": collection,
        "created": created,
        "points": len(points),
        "graph_collection": graph_collection,
        "graph_points": len(graph_points),
    }

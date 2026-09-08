"""Tạo full, linked và relational context theo token budget có audit trail."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..offline.example_index import retrieve_similar_examples
from ..offline.schema_catalog import load_schema_catalog, render_full_ddl
from ..settings import RetrievalSettings, Settings
from .retrieval import retrieve
from .schema_linking import link_literal_values, link_schema_elements


def estimate_tokens(text: str) -> int:
    return max(1, (len(text) + 3) // 4)


def _render_item(item: dict[str, Any]) -> str:
    return f"[{item['kind'].upper()} id={item['id']} source={item['source']}]\n{item['text']}"


def select_evidence_bundle(
    items: list[dict[str, Any]],
    *,
    token_budget: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if token_budget < 1:
        raise ValueError("token_budget phải lớn hơn 0")
    priority = {"schema": 0, "value": 1, "business": 2, "example": 3, "event": 4}
    unique = {item["id"]: item for item in items}
    ordered = sorted(
        unique.values(),
        key=lambda item: (priority.get(item["kind"], 99), -float(item.get("score", 0)), item["id"]),
    )
    selected = []
    trace = []
    used = 0
    for item in ordered:
        cost = estimate_tokens(_render_item(item))
        keep = not selected or used + cost <= token_budget
        trace.append({"id": item["id"], "tokens": cost, "kept": keep, "reason": "budget" if not keep else "selected"})
        if keep:
            selected.append(item)
            used += cost
    return selected, trace


def build_full_context(
    question: str,
    evidence: str,
    schema_catalog_path: str | Path,
    business_path: str | Path,
) -> tuple[str, list[dict[str, Any]], dict[str, Any]]:
    catalog = load_schema_catalog(schema_catalog_path)
    business = Path(business_path).read_text(encoding="utf-8")
    ddl = render_full_ddl(catalog)
    context = (
        f"<bird_evidence>\n{evidence or 'Không có'}\n</bird_evidence>\n\n"
        f"<database_schema>\n{ddl}\n</database_schema>\n\n"
        f"<business_document source=\"{Path(business_path).resolve()}\">\n{business}\n</business_document>"
    )
    items = [
        {
            "id": f"full:{catalog['database_id']}:schema",
            "kind": "schema",
            "text": ddl,
            "source": catalog["database_path"],
            "score": 1.0,
            "metadata": {"full_context": True},
        },
        {
            "id": f"full:{catalog['database_id']}:business",
            "kind": "business",
            "text": business,
            "source": str(Path(business_path).resolve()),
            "score": 1.0,
            "metadata": {"full_context": True},
        },
    ]
    return context, items, {"estimated_tokens": estimate_tokens(context), "question_tokens": estimate_tokens(question)}


def _retrieval_settings(settings: Settings, parameters: dict[str, Any]) -> Settings:
    allowed = {
        key: parameters[key]
        for key in (
            "mode",
            "candidate_k",
            "docs_top_k",
            "semantic_weight",
            "keyword_weight",
            "rrf_k",
            "rerank_top_k",
            "rerank_enabled",
            "rerank_max_length",
            "rerank_batch_size",
            "min_score",
        )
        if key in parameters
    }
    retrieval = RetrievalSettings.model_validate({**settings.retrieval.model_dump(), **allowed})
    return settings.model_copy(update={"retrieval": retrieval})


def retrieve_hybrid_evidence(
    question: str,
    *,
    knowledge_id: str,
    doc_id: str,
    settings: Settings,
    parameters: dict[str, Any],
) -> list[dict[str, Any]]:
    app = _retrieval_settings(settings, parameters)
    hits = retrieve(
        question,
        kind="docs",
        knowledge_id=knowledge_id,
        include_doc_ids={doc_id},
        settings=app,
    )
    return [
        {
            "id": f"business:{hit['metadata'].get('id') or hit['metadata'].get('parent_id') or index}",
            "kind": "business",
            "text": hit["text"],
            "source": str(hit["metadata"].get("source") or doc_id),
            "score": float(hit["score"]),
            "metadata": {**hit["metadata"], "retrieval_mode": app.retrieval.mode},
        }
        for index, hit in enumerate(hits, 1)
    ]


def build_linked_context(
    question: str,
    evidence: str,
    schema_catalog_path: str | Path,
    *,
    knowledge_id: str,
    doc_id: str,
    settings: Settings,
    parameters: dict[str, Any],
    example_index: dict[str, Any] | None = None,
) -> tuple[str, list[dict[str, Any]], list[dict[str, Any]]]:
    catalog = load_schema_catalog(schema_catalog_path)
    schema_items = link_schema_elements(
        question,
        catalog,
        table_k=int(parameters.get("table_k", 5)),
        column_k=int(parameters.get("column_k", 12)),
        min_score=float(parameters.get("schema_min_score", 0.12)),
    )
    value_items = link_literal_values(
        f"{question} {evidence}",
        catalog,
        top_k=int(parameters.get("value_k", 10)),
        fuzzy_threshold=float(parameters.get("value_fuzzy_threshold", 0.84)),
    )
    business_items = retrieve_hybrid_evidence(
        question,
        knowledge_id=knowledge_id,
        doc_id=doc_id,
        settings=settings,
        parameters=parameters,
    )
    example_items = retrieve_similar_examples(
        question,
        example_index,
        database_id=catalog["database_id"],
        top_k=int(parameters.get("example_k", 3)),
    )
    bird_item = {
        "id": f"bird-evidence:{catalog['database_id']}",
        "kind": "business",
        "text": f"BIRD evidence: {evidence or 'Không có'}",
        "source": "bird-case-evidence",
        "score": 100.0,
        "metadata": {"provided_with_question": True},
    }
    selected, trace = select_evidence_bundle(
        [bird_item, *schema_items, *value_items, *business_items, *example_items],
        token_budget=int(parameters.get("token_budget", 5000)),
    )
    context = "\n\n".join(_render_item(item) for item in selected)
    trace.append(
        {
            "summary": {
                "schema": len(schema_items),
                "value": len(value_items),
                "business": len(business_items),
                "example": len(example_items),
                "selected": len(selected),
                "estimated_tokens": estimate_tokens(context),
                "example_corpus": "train" if example_index else "unavailable",
            }
        }
    )
    return context, selected, trace


def load_optional_example_index(path: str | Path | None) -> dict[str, Any] | None:
    if path is None or not Path(path).is_file():
        return None
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if value.get("corpus_split") != "train":
        raise ValueError("example artifact không thuộc train split")
    return value

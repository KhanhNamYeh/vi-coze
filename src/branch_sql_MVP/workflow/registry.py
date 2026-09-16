"""Single registry for reusable workflow node types."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

@dataclass(frozen=True)
class NodeType:
    type: str
    label: str
    description: str
    config_schema: dict[str, Any]
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    executor: Callable[..., dict[str, Any]] | None = None

def _passthrough(inputs: dict[str, Any], config: dict[str, Any], **_: Any) -> dict[str, Any]:
    return {"value": config.get("value", inputs.get("value"))}

def _start(inputs: dict[str, Any], config: dict[str, Any], *, state=None, **_: Any) -> dict[str, Any]:
    values = {"example_index_path": None, **dict((state or {}).get("inputs", {}))}
    values.update(inputs)
    return values or {"question": config.get("question", "")}

def _condition(inputs: dict[str, Any], config: dict[str, Any], **_: Any) -> dict[str, Any]:
    route = config.get("route") or inputs.get("route")
    if not isinstance(route, str) or not route:
        raise ValueError("condition cần route string")
    return {"route": route}

def _context(inputs: dict[str, Any], config: dict[str, Any], *, settings=None, **_: Any) -> dict[str, Any]:
    """Build context through the same adapters used by the online pipelines."""
    from ..online.context_builder import (
        build_full_context,
        build_linked_context,
        load_optional_example_index,
        select_evidence_bundle,
    )
    from ..settings import load_settings

    values = {**config, **inputs}
    mode = values.get("mode", "direct")
    question = str(values.get("question", "")).strip()
    evidence = str(values.get("evidence", ""))
    if mode == "linked_parts":
        from .nodes.linking import linked_evidence
        return linked_evidence(inputs,config)
    if mode == "direct":
        value = values.get("context")
        if value is None:
            raise ValueError("context_builder direct cần input context")
        return {"text": str(value), "items": list(values.get("items", [])), "trace": []}
    if not question:
        raise ValueError("context_builder cần question")
    if mode == "full":
        schema = values.get("schema_catalog_path")
        business = values.get("business_path")
        if not schema or not business:
            raise ValueError("context_builder full cần schema_catalog_path và business_path")
        text, items, audit = build_full_context(question, evidence, schema, business)
        return {"text": text, "items": items, "trace": [audit]}
    if mode == "linked":
        schema = values.get("schema_catalog_path")
        knowledge_id = values.get("knowledge_id")
        doc_id = values.get("doc_id")
        if not schema or not knowledge_id or not doc_id:
            raise ValueError("context_builder linked cần schema_catalog_path, knowledge_id và doc_id")
        parameters = dict(values.get("parameters", {}))
        example_index = load_optional_example_index(values.get("example_index_path"))
        text, items, trace = build_linked_context(
            question, evidence, schema, knowledge_id=str(knowledge_id), doc_id=str(doc_id),
            settings=settings or load_settings(), parameters=parameters, example_index=example_index,
        )
        return {"text": text, "items": items, "trace": trace}
    if mode == "evidence_bundle":
        raw_items = values.get("items")
        if not isinstance(raw_items, list):
            raise ValueError("context_builder evidence_bundle cần input items")
        selected, trace = select_evidence_bundle(raw_items, token_budget=int(values.get("token_budget", 5000)))
        text = "\n\n".join(
            f"[{item['kind'].upper()} id={item['id']} source={item['source']}]\n{item['text']}" for item in selected
        )
        return {"text": text, "items": selected, "trace": trace}
    raise ValueError(f"context_builder không hỗ trợ mode '{mode}'")

def _retrieval(inputs: dict[str, Any], config: dict[str, Any], *, settings=None, **_: Any) -> dict[str, Any]:
    from ..online.retrieval import retrieve
    from ..settings import load_settings

    values = {**config, **inputs}
    if values.get("format") == "business":
        from .nodes.linking import business_retrieval
        return business_retrieval(inputs,config,settings=settings or load_settings())
    from ..online.context_builder import _retrieval_settings
    settings = _retrieval_settings(settings or load_settings(),config)
    query = str(values.get("query") or values.get("question") or "").strip()
    if not query:
        raise ValueError("retrieval cần query hoặc question")
    kind = str(values.get("kind", "docs"))
    if kind not in {"docs", "sql", "graph"}:
        raise ValueError("retrieval kind phải là docs, sql hoặc graph")
    hits = retrieve(
        query, kind=kind, knowledge_id=values.get("knowledge_id"),
        settings=settings or load_settings(),
    )
    return {"items": hits, "query": query, "kind": kind}

def _sql_executor(inputs: dict[str, Any], config: dict[str, Any], **_: Any) -> dict[str, Any]:
    from ..online.sql_execution import execute_readonly_sql
    database = inputs.get("database", config.get("database"))
    sql = inputs.get("sql", config.get("sql"))
    if not database or not sql:
        raise ValueError("sql_executor cần database và sql")
    observation = execute_readonly_sql(database, sql, timeout_seconds=float(config.get("timeout_seconds", 5)), max_rows=int(config.get("max_rows", 500)), preview_rows=int(config.get("preview_rows",config.get("max_rows",500)))).model_dump(mode="json")
    observation["truncated"] = observation["truncated"] or observation["row_count"] > len(observation.get("preview", []))
    observation.update(candidate_id=inputs.get("candidate_id"), rows=observation.get("preview", []),
                       row_count_returned=len(observation.get("preview", [])))
    return {"observation": observation}

def _output(inputs: dict[str, Any], config: dict[str, Any], **_: Any) -> dict[str, Any]:
    return {"result": inputs.get("result", config.get("result"))}

def _unimplemented(inputs: dict[str, Any], config: dict[str, Any], **_: Any) -> dict[str, Any]:
    raise RuntimeError(f"node type chưa có adapter runtime: {config.get('type', 'domain')}")

def _llm_placeholder(*_: Any, **__: Any) -> dict[str, Any]:
    from .nodes.llm import invoke_llm
    return invoke_llm(*_, **__)

_TYPES = [
    NodeType("bounded_loop", "Bounded loop", "Run a visible child workflow with a strict iteration bound", {"type": "object", "required": ["body", "max_iterations"]}, {"type": "object"}, {"iterations": {"type": "array"}}, _passthrough),
    NodeType("foreach", "For each / collect", "Run a child workflow per item and collect every invocation", {"type": "object", "required": ["body", "max_items"]}, {"type": "object"}, {"items": {"type": "array"}}, _passthrough),
    NodeType("start", "Start", "Workflow inputs", {}, {}, {"question": {"type": "string"}}, _start),
    NodeType("llm", "LLM", "Reusable prompt/model call", {"type": "object", "properties": {"system_prompt": {"type": "string"}, "user_prompt": {"type": "string"}, "response_format": {"enum": ["text", "json"]}, "output_schema": {"type": "object"}}, "required": ["user_prompt"]}, {"type": "object"}, {"text": {"type": "string"}, "json": {"type": "object"}, "usage": {"type": "object"}, "model": {"type": "string"}, "latency": {"type": "number"}}, _llm_placeholder),
    NodeType("context_builder", "Context builder", "Full, linked, or budgeted evidence context", {"type": "object", "properties": {"mode": {"enum": ["direct", "full", "linked", "linked_parts", "evidence_bundle"]}}}, {"type": "object"}, {"text": {"type": "string"}, "items": {"type": "array"}, "trace": {"type": "array"}}, _context),
    NodeType("retrieval", "Retrieval", "Qdrant semantic, keyword, or hybrid retrieval", {"type": "object", "properties": {"kind": {"enum": ["docs", "sql", "graph"]}, "knowledge_id": {"type": "string"}}}, {"type": "object"}, {"items": {"type": "array"}}, _retrieval),
    NodeType("sql_executor", "SQL executor", "Read-only SQLite execution", {"type": "object"}, {"type": "object"}, {"observation": {"type": "object"}}, _sql_executor),
    NodeType("condition", "Condition", "Bounded branch decision", {"type": "object"}, {"type": "object"}, {"route": {"type": "string"}}, _condition),
    NodeType("output", "Output", "Workflow output", {}, {"type": "object"}, {"result": {"type": "object"}}, _output),
    NodeType("passthrough", "Passthrough", "Contract-test utility", {"type": "object"}, {"type": "object"}, {"value": {}}, _passthrough),
]

def node_registry() -> dict[str, NodeType]:
    from .nodes import domain
    result = {item.type: item for item in _TYPES}
    for name in ("events", "evidence_filter", "branch", "merge", "candidate", "candidate_select", "strategies", "answer_guard", "result"):
        result[name] = NodeType(name, name.replace("_", " ").title(), "Shared deterministic adapter", {"type": "object"}, {"type": "object"}, {}, getattr(domain, name))
    from .nodes import linking
    for name in ("schema_link", "value_link", "example_retrieval"):
        result[name] = NodeType(name,name.replace("_"," ").title(),"Shared schema/value/retrieval algorithm",
            {"type":"object"},{"type":"object"},{},getattr(linking,name))
    from .nodes import offline_graph
    for name in ("graph_prepare", "graph_resolve", "graph_write"):
        result[name] = NodeType(name,name.replace("_"," ").title(),"Deterministic GraphRAG adapter",{}, {}, {},getattr(offline_graph,name))
    from .nodes.offline import stage
    from functools import partial
    for name in ("validate", "preprocess", "schema", "event", "extract", "link", "chunk", "embed", "index", "register"):
        def adapter(inputs, config, *, operation=name, **kwargs):
            return stage(inputs, {**config, "stage": operation}, **kwargs)
        result["offline_"+name] = NodeType("offline_"+name, "Offline " + name, "Offline artifact adapter", {"type":"object"}, {"type":"object"}, {}, adapter)
    return result

def node_type_metadata() -> list[dict[str, Any]]:
    return [{"type": item.type, "label": item.label, "description": item.description, "config_schema": item.config_schema, "input_schema": item.input_schema, "output_schema": item.output_schema} for item in node_registry().values()]

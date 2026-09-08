"""LLM SQL graph agent -> deterministic resolution, communities and indexing data."""

from __future__ import annotations

import hashlib
import html
import json
import re

from pydantic import BaseModel, Field

from ..settings import GraphSettings, Settings, load_settings
from .chunk import load_chunks


class ExtractedEntity(BaseModel):
    name: str = Field(min_length=1)
    type: str = Field(min_length=1)
    description: str = Field(min_length=1)
    evidence: str = Field(min_length=1)


class ExtractedRelationship(BaseModel):
    source: str = Field(min_length=1)
    target: str = Field(min_length=1)
    type: str = Field(min_length=1)
    description: str = Field(min_length=1)
    evidence: str = Field(min_length=1)


class ExtractedGraph(BaseModel):
    entities: list[ExtractedEntity] = Field(default_factory=list)
    relationships: list[ExtractedRelationship] = Field(default_factory=list)


class CommunitySummary(BaseModel):
    title: str = Field(min_length=1)
    summary: str = Field(min_length=1)


class SQLGraphAgent:
    """Một LLM agent, hai tác vụ structured: extract chunk và summarize community."""

    def __init__(self, model, settings: GraphSettings):
        self.settings = settings
        self.extractor = model.with_structured_output(ExtractedGraph)
        self.summarizer = model.with_structured_output(CommunitySummary)
        self.calls = 0

    def _invoke(self, runnable, messages, schema):
        last_error: Exception | None = None
        for _ in range(self.settings.output_retries + 1):
            try:
                self.calls += 1
                value = runnable.invoke(messages)
                return value if isinstance(value, schema) else schema.model_validate(value)
            except Exception as error:
                last_error = error
        raise RuntimeError(f"LLM structured output không hợp lệ: {last_error}") from last_error

    def extract(self, *, chunk_id: str, source_kind: str, text: str) -> ExtractedGraph:
        return self._invoke(
            self.extractor,
            [
                ("system", self.settings.agent_prompt),
                (
                    "human",
                    f"Chunk ID: {chunk_id}\n"
                    f"Source kind: {source_kind}\n"
                    f"Allowed entity types: {', '.join(self.settings.entity_types)}\n"
                    f"Allowed relationship types: {', '.join(self.settings.relationship_types)}\n\n"
                    f"CHUNK:\n{text}",
                ),
            ],
            ExtractedGraph,
        )

    def summarize(self, *, community_id: str, context: str) -> CommunitySummary:
        return self._invoke(
            self.summarizer,
            [
                ("system", self.settings.report_prompt),
                ("human", f"Community ID: {community_id}\n\nGRAPH COMMUNITY:\n{context}"),
            ],
            CommunitySummary,
        )


def _id(*values: str) -> str:
    return hashlib.sha256("\0".join(values).encode("utf-8")).hexdigest()[:24]


def _clean(value: str) -> str:
    value = value.replace("\\_", "_").replace("`", "").replace("**", "")
    return re.sub(r"\s+", " ", value).strip(" \t\r\n|:;,.-")


def _key(value: str) -> str:
    return re.sub(r"\s+", " ", _clean(value)).casefold()


def _allowed(value: str, allowed: list[str]) -> bool:
    return value.strip().casefold() in {item.casefold() for item in allowed}


def _append_unique(items: list, value) -> None:
    if value and value not in items:
        items.append(value)


def _resolve(
    extractions: list[tuple[str, str, ExtractedGraph]],
    cfg: GraphSettings,
) -> tuple[list[dict], list[dict], dict]:
    """Validate and merge structured deltas; this function never extracts SQL facts."""
    merged: dict[tuple[str, str], dict] = {}
    raw_relationships: list[tuple[str, str, ExtractedRelationship]] = []
    raw_entities = 0

    for chunk_id, source_kind, extraction in extractions:
        for item in extraction.entities:
            entity_type = item.type.strip().casefold()
            name = _clean(item.name)
            if not name or not _allowed(entity_type, cfg.entity_types):
                continue
            raw_entities += 1
            key = (entity_type, _key(name))
            row = merged.setdefault(key, {
                "id": _id("entity", entity_type, _key(name)),
                "name": name,
                "type": entity_type,
                "descriptions": [],
                "source_chunk_ids": [],
                "source_kinds": [],
                "evidence": [],
            })
            _append_unique(row["descriptions"], _clean(item.description))
            _append_unique(row["source_chunk_ids"], chunk_id)
            _append_unique(row["source_kinds"], source_kind)
            _append_unique(row["evidence"], {
                "chunk_id": chunk_id,
                "kind": source_kind,
                "text": _clean(item.evidence),
            })
        raw_relationships.extend((chunk_id, source_kind, item) for item in extraction.relationships)

    entities: list[dict] = []
    by_name: dict[str, list[dict]] = {}
    for row in merged.values():
        entity = {
            "id": row["id"],
            "name": row["name"],
            "type": row["type"],
            "description": " | ".join(row["descriptions"]),
            "source_chunk_ids": row["source_chunk_ids"],
            "source_kinds": row["source_kinds"],
            "evidence": row["evidence"],
        }
        entities.append(entity)
        by_name.setdefault(_key(entity["name"]), []).append(entity)

    relationships: dict[tuple[str, str, str], dict] = {}
    invalid = 0
    for chunk_id, source_kind, item in raw_relationships:
        relation_type = item.type.strip().casefold()
        if not _allowed(relation_type, cfg.relationship_types):
            invalid += 1
            continue
        sources = by_name.get(_key(item.source), [])
        targets = by_name.get(_key(item.target), [])
        if len(sources) != 1 or len(targets) != 1 or sources[0]["id"] == targets[0]["id"]:
            invalid += 1
            continue
        source, target = sources[0], targets[0]
        key = (source["id"], target["id"], relation_type)
        row = relationships.setdefault(key, {
            "id": _id("relationship", *key),
            "source": source["id"],
            "target": target["id"],
            "type": relation_type,
            "descriptions": [],
            "source_chunk_ids": [],
            "source_kinds": [],
            "evidence": [],
            "weight": 0,
        })
        _append_unique(row["descriptions"], _clean(item.description))
        _append_unique(row["source_chunk_ids"], chunk_id)
        _append_unique(row["source_kinds"], source_kind)
        _append_unique(row["evidence"], {
            "chunk_id": chunk_id,
            "kind": source_kind,
            "text": _clean(item.evidence),
        })
        row["weight"] += 1

    edges = [{
        **{key: value for key, value in row.items() if key != "descriptions"},
        "description": " | ".join(row["descriptions"]),
    } for row in relationships.values()]
    return entities, edges, {
        "raw_entities": raw_entities,
        "duplicate_entities_merged": raw_entities - len(entities),
        "raw_relationships": len(raw_relationships),
        "invalid_relationships": invalid,
    }


def _communities(nodes: list[dict], edges: list[dict], cfg: GraphSettings):
    import networkx as nx

    graph = nx.Graph()
    graph.add_nodes_from((node["id"], node) for node in nodes)
    for edge in edges:
        graph.add_edge(edge["source"], edge["target"], weight=edge["weight"], id=edge["id"])
    if not graph.nodes:
        return graph, []
    if not graph.edges or cfg.community_algorithm == "connected_components":
        groups = list(nx.connected_components(graph))
    elif cfg.community_algorithm == "greedy_modularity":
        groups = list(nx.community.greedy_modularity_communities(graph, weight="weight"))
    else:
        groups = list(nx.community.louvain_communities(
            graph,
            weight="weight",
            resolution=cfg.community_resolution,
            seed=cfg.random_seed,
        ))
    ordered = sorted((sorted(group) for group in groups), key=lambda group: (-len(group), group[0]))
    communities = [{"id": f"community_{index:03d}", "node_ids": group} for index, group in enumerate(ordered, 1)]
    membership = {node_id: community["id"] for community in communities for node_id in community["node_ids"]}
    for node in nodes:
        node["community_id"] = membership[node["id"]]
    return graph, communities


def _community_context(community: dict, nodes: list[dict], edges: list[dict]) -> str:
    members = set(community["node_ids"])
    selected_nodes = [node for node in nodes if node["id"] in members]
    selected_edges = [edge for edge in edges if edge["source"] in members and edge["target"] in members]
    labels = {node["id"]: node["name"] for node in selected_nodes}
    entity_lines = [f"{node['type']}: {node['name']} — {node['description']}" for node in selected_nodes]
    relation_lines = [
        f"{labels[edge['source']]} -[{edge['type']}]-> {labels[edge['target']]} — {edge['description']}"
        for edge in selected_edges
    ]
    return "\n".join(entity_lines + relation_lines)


def _reports(
    doc_id: str,
    communities: list[dict],
    nodes: list[dict],
    edges: list[dict],
    cfg: GraphSettings,
    agent: SQLGraphAgent,
) -> tuple[list[dict], list[dict]]:
    if not cfg.generate_reports or cfg.max_reports == 0:
        return [], []
    reports: list[dict] = []
    errors: list[dict] = []
    by_id = {node["id"]: node for node in nodes}
    for community in communities[: cfg.max_reports]:
        try:
            summary = agent.summarize(
                community_id=community["id"],
                context=_community_context(community, nodes, edges),
            )
        except Exception as error:
            errors.append({"community_id": community["id"], "error": str(error)})
            continue
        member_nodes = [by_id[node_id] for node_id in community["node_ids"]]
        reports.append({
            "id": _id("report", doc_id, community["id"]),
            "community_id": community["id"],
            "title": _clean(summary.title),
            "text": summary.summary.strip(),
            "node_ids": community["node_ids"],
            "source_chunk_ids": list(dict.fromkeys(
                chunk_id for node in member_nodes for chunk_id in node["source_chunk_ids"]
            )),
            "source_kinds": list(dict.fromkeys(
                source_kind for node in member_nodes for source_kind in node["source_kinds"]
            )),
        })
    return reports, errors


def run(
    doc_id: str,
    *,
    kind: str = "docs",
    provider: str | None = None,
    model: str | None = None,
    api_key: str | None = None,
    artifact_tag: str | None = None,
    settings: Settings | None = None,
) -> dict:
    app = settings or load_settings()
    cfg = app.graph
    if not cfg.enabled:
        return {"doc_id": doc_id, "enabled": False, "skipped": True, "reason": "graph.enabled=false"}
    if kind not in cfg.source_kinds:
        return {"doc_id": doc_id, "enabled": True, "skipped": True, "reason": f"kind '{kind}' không thuộc graph.source_kinds"}

    from ..online.api import build_model

    chunks = load_chunks(doc_id, settings=app)
    chunks = chunks[: cfg.max_chunks] if cfg.max_chunks else chunks
    llm = build_model(
        settings=app,
        provider=provider or cfg.provider,
        model=model or cfg.model,
        api_key=api_key,
        model_options={"temperature": cfg.temperature},
    )
    agent = SQLGraphAgent(llm, cfg)

    extractions: list[tuple[str, str, ExtractedGraph]] = []
    errors: list[dict] = []
    for chunk in chunks:
        try:
            extracted = agent.extract(chunk_id=chunk["id"], source_kind=kind, text=chunk["text"])
            extractions.append((chunk["id"], kind, extracted))
        except Exception as error:
            errors.append({"chunk_id": chunk["id"], "kind": kind, "error": str(error)})

    nodes, edges, resolution = _resolve(extractions, cfg)
    if not nodes:
        raise ValueError("graph tạo ra 0 entity; kiểm tra chunks, API model và entity_types")
    graph, communities = _communities(nodes, edges, cfg)
    reports, report_errors = _reports(doc_id, communities, nodes, edges, cfg, agent)
    stats = {
        **resolution,
        "chunks": len(chunks),
        "failed_chunks": len(errors),
        "nodes": len(nodes),
        "edges": len(edges),
        "isolated_nodes": len(list(__import__("networkx").isolates(graph))),
        "communities": len(communities),
        "reports": len(reports),
        "failed_reports": len(report_errors),
        "llm_calls": agent.calls,
    }
    result = {
        "doc_id": doc_id,
        "kind": kind,
        "agent": "sql_graph_agent",
        "method": "llm",
        "parameters": cfg.model_dump(mode="json"),
        "stats": stats,
        "nodes": nodes,
        "edges": edges,
        "communities": communities,
        "reports": reports,
        "errors": {"chunks": errors, "reports": report_errors},
    }
    suffix = _artifact_suffix(artifact_tag)
    output = app.path(app.paths.artifacts) / f"{doc_id}{suffix}.graph.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"doc_id": doc_id, "enabled": True, "skipped": False, "path": str(output), **stats}


def _artifact_suffix(artifact_tag: str | None) -> str:
    if artifact_tag is None:
        return ""
    tag = artifact_tag.strip().lower()
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", tag):
        raise ValueError("artifact_tag chỉ được chứa a-z, 0-9, '_' hoặc '-'")
    return f".{tag}"


def load(
    doc_id: str,
    *,
    artifact_tag: str | None = None,
    settings: Settings | None = None,
) -> dict:
    app = settings or load_settings()
    suffix = _artifact_suffix(artifact_tag)
    path = app.path(app.paths.artifacts) / f"{doc_id}{suffix}.graph.json"
    if not path.exists():
        raise FileNotFoundError(f"chưa có {path.name}; chạy graph trước")
    return json.loads(path.read_text(encoding="utf-8"))


def embedding_items(doc_id: str, *, settings: Settings | None = None) -> list[dict]:
    data = load(doc_id, settings=settings)
    items = [{
        "id": node["id"],
        "kind": "graph_entity",
        "text": f"{node['type']}: {node['name']}\n{node['description']}".strip(),
        "metadata": node,
    } for node in data["nodes"]]
    items.extend({
        "id": report["id"],
        "kind": "graph_report",
        "text": report["text"],
        "metadata": report,
    } for report in data["reports"] if report["text"].strip())
    return items


def html_view(doc_id: str, *, settings: Settings | None = None) -> str:
    import networkx as nx

    app = settings or load_settings()
    data = load(doc_id, settings=app)
    graph = nx.Graph()
    graph.add_nodes_from((node["id"], node) for node in data["nodes"])
    graph.add_edges_from((edge["source"], edge["target"], edge) for edge in data["edges"])
    limit = app.graph.visualization_max_nodes
    if len(graph) > limit:
        selected = [node for node, _ in sorted(graph.degree, key=lambda item: (-item[1], item[0]))[:limit]]
        graph = graph.subgraph(selected).copy()
    width, height, pad = 1100, 680, 45
    if len(graph) == 1:
        positions = {next(iter(graph)): (0.0, 0.0)}
    else:
        positions = nx.spring_layout(graph, seed=app.graph.random_seed, weight="weight")

    def point(node_id: str) -> tuple[float, float]:
        x, y = positions[node_id]
        return pad + (float(x) + 1) * (width - 2 * pad) / 2, pad + (float(y) + 1) * (height - 2 * pad) / 2

    colors = {"table": "#f59e0b", "column": "#38bdf8", "business_rule": "#a78bfa", "sql_function": "#34d399"}
    edge_svg = "".join(
        f'<line x1="{point(a)[0]:.1f}" y1="{point(a)[1]:.1f}" x2="{point(b)[0]:.1f}" y2="{point(b)[1]:.1f}" stroke="#64748b" stroke-opacity=".45" stroke-width="1.4"><title>{html.escape(str(meta.get("type", "relationship")))}</title></line>'
        for a, b, meta in graph.edges(data=True)
    )
    node_svg = ""
    for node_id, node in graph.nodes(data=True):
        x, y = point(node_id)
        name = str(node.get("name", node_id))
        label = name if len(name) <= 24 else name[:21] + "…"
        color = colors.get(str(node.get("type")), "#fb7185")
        tooltip = html.escape(f"{node.get('type', '')}: {name}\n{node.get('description', '')}")
        node_svg += (
            f'<g><circle cx="{x:.1f}" cy="{y:.1f}" r="9" fill="{color}" stroke="#0f172a" stroke-width="1.5"><title>{tooltip}</title></circle>'
            f'<text x="{x + 12:.1f}" y="{y + 4:.1f}" fill="#e2e8f0" font-size="11">{html.escape(label)}</text></g>'
        )
    return (
        '<div style="background:#0f172a;border-radius:12px;padding:10px;overflow:auto">'
        f'<div style="color:#cbd5e1;margin:4px 8px 10px">{len(graph.nodes)} nodes · {len(graph.edges)} edges · hover node để xem chi tiết</div>'
        f'<svg viewBox="0 0 {width} {height}" style="width:100%;min-width:760px;height:680px">{edge_svg}{node_svg}</svg></div>'
    )

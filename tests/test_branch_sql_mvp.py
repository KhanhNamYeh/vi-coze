import json
import uuid
from pathlib import Path

import pytest

from src.branch_sql_MVP.offline.chunk import build
from src.branch_sql_MVP.offline.extract import extract
from src.branch_sql_MVP.offline.link import link
from src.branch_sql_MVP.offline.graph import (
    CommunitySummary,
    ExtractedEntity,
    ExtractedGraph,
    ExtractedRelationship,
    SQLGraphAgent,
    _communities,
    _resolve,
)
from src.branch_sql_MVP.preprocess.xlsx_parse import to_markdown
from src.branch_sql_MVP.preprocess.docx_parse import _normalize_record_headings
from src.branch_sql_MVP.settings import load_settings


MARKDOWN = """# Tài liệu

## CASE_01

### question

Tìm khách hàng mới.

### statement

| field | meaning |
| --- | --- |
| customer_id | mã khách hàng |
"""


def test_extract_has_only_three_basic_types_and_link_adds_parent():
    elements = extract(MARKDOWN)
    assert {element["type"] for element in elements} == {"heading", "table", "text"}

    linked = link(elements)
    case = next(element for element in linked if element["type"] == "heading" and element["text"] == "CASE_01")
    question = next(element for element in linked if element["type"] == "heading" and element["text"] == "question")
    body = next(element for element in linked if element["type"] == "text")
    assert question["parent_id"] == case["id"]
    assert body["parent_id"] == question["id"]


def test_chunk_is_one_parent_child_flow_without_mode_setting():
    settings = load_settings()
    cfg = settings.chunk.model_copy(
        update={"unit": "character", "child_min": 1, "child_max": 160, "child_overlap": 10}
    )
    children, parents = build(
        {"doc_id": "sample", "source": "sample.md", "elements": link(extract(MARKDOWN))},
        cfg,
        settings.embedding.dense_model,
    )
    assert not hasattr(cfg, "mode")
    assert children and parents
    assert {child["parent_id"] for child in children} <= {parent["id"] for parent in parents}
    assert all(child["text"].strip() for child in children)
    assert all(child["section_id"] == "CASE_01" for child in children)
    assert all(child["text"].count("CASE_01") == 1 for child in children)


def test_chunk_requires_configured_heading_level_instead_of_falling_back():
    settings = load_settings()
    cfg = settings.chunk.model_copy(update={"unit": "character", "child_min": 1})
    elements = link(extract("# Chỉ có H1\n\nNội dung."))
    with pytest.raises(ValueError, match="yêu cầu H2"):
        build({"doc_id": "h1", "source": "h1.md", "elements": elements}, cfg, "")


def test_docx_numbered_bold_bullets_become_configured_record_heading():
    markdown = "# Danh mục\n\n* 1. **Bảng khách hàng**\n\nNội dung"
    normalized = _normalize_record_headings(markdown, 2)
    assert "## Bảng khách hàng" in normalized
    assert "* 1." not in normalized


def test_xlsx_uses_workbook_headers_as_level_three_features(tmp_path: Path):
    import openpyxl

    source = tmp_path / "samples.xlsx"
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "train"
    sheet.append(["sample_id", "natural_question", "generated_statement", "Relevant Chunks"])
    sheet.append(["S01", "câu hỏi", "SELECT 1", "GOLD_TABLE"])
    workbook.save(source)

    settings = load_settings().preprocess.model_copy(
        update={"excel_sheets": [], "excel_id_column": "sample_id"}
    )
    markdown = to_markdown(source, settings)
    assert "## S01" in markdown
    assert "### natural_question\ncâu hỏi" in markdown
    assert "### generated_statement\nSELECT 1" in markdown
    assert "Relevant Chunks" not in markdown
    assert "GOLD_TABLE" not in markdown
    assert "### query" not in markdown


def test_api_and_llm_settings_are_separate():
    settings = load_settings()
    assert settings.api.provider in settings.api.providers
    assert settings.api.model
    assert settings.llm.system_prompt
    assert not hasattr(settings.llm, "providers")


def test_knowledge_ids_use_separate_docs_and_sql_collections():
    settings = load_settings()
    assert {"p1", "p2"} <= set(settings.index.collections)
    assert settings.index.collection("p1", "docs") == "sqlp1__docs"
    assert settings.index.collection("p1", "sql") == "sqlp1__sql"
    assert settings.index.collection("p2", "docs") == "sqlp2__docs"
    assert settings.index.collection("p2", "sql") == "sqlp2__sql"
    assert settings.index.collection("p1", "graph") == "sqlp1__graph"
    assert settings.index.collection("p2", "graph") == "sqlp2__graph"
    assert len({name for pair in settings.index.collections.values() for name in pair.values()}) == 6


def test_graph_resolver_keeps_docs_and_sql_chunk_evidence():
    settings = load_settings()
    docs = ExtractedGraph(
        entities=[
            ExtractedEntity(name="ORDERS", type="table", description="Đơn hàng", evidence="Bảng ORDERS"),
            ExtractedEntity(name="ORDERS.ORDER_ID", type="column", description="Mã đơn", evidence="ORDER_ID"),
        ],
        relationships=[ExtractedRelationship(
            source="ORDERS",
            target="ORDERS.ORDER_ID",
            type="table_has_column",
            description="ORDER_ID thuộc ORDERS",
            evidence="ORDERS có cột ORDER_ID",
        )],
    )
    sql = ExtractedGraph(
        entities=[ExtractedEntity(
            name="ORDERS",
            type="table",
            description="Bảng trong câu SQL mẫu",
            evidence="FROM ORDERS",
        )],
    )
    nodes, edges, stats = _resolve(
        [("docs_chunk", "docs", docs), ("sql_chunk", "sql", sql)],
        settings.graph,
    )
    graph, communities = _communities(nodes, edges, settings.graph)

    assert {node["name"] for node in nodes} == {"ORDERS", "ORDERS.ORDER_ID"}
    assert {edge["type"] for edge in edges} == {"table_has_column"}
    orders = next(node for node in nodes if node["name"] == "ORDERS")
    assert orders["source_chunk_ids"] == ["docs_chunk", "sql_chunk"]
    assert orders["source_kinds"] == ["docs", "sql"]
    assert {item["kind"] for item in orders["evidence"]} == {"docs", "sql"}
    assert stats["invalid_relationships"] == 0
    assert graph.number_of_nodes() == 2
    assert len(communities) == 1


def test_one_sql_graph_agent_handles_extract_and_summary_with_structured_output():
    settings = load_settings()

    class Structured:
        def __init__(self, schema):
            self.schema = schema

        def invoke(self, _messages):
            if self.schema is ExtractedGraph:
                return {
                    "entities": [{
                        "name": "CUSTOMERS",
                        "type": "table",
                        "description": "Khách hàng",
                        "evidence": "FROM CUSTOMERS",
                    }],
                    "relationships": [],
                }
            return {"title": "Customers", "summary": "Community chứa bảng CUSTOMERS."}

    class Model:
        def with_structured_output(self, schema):
            return Structured(schema)

    agent = SQLGraphAgent(Model(), settings.graph)
    extracted = agent.extract(chunk_id="sql_1", source_kind="sql", text="SELECT * FROM CUSTOMERS")
    summary = agent.summarize(community_id="community_001", context="table: CUSTOMERS")

    assert extracted.entities[0].name == "CUSTOMERS"
    assert isinstance(summary, CommunitySummary)
    assert agent.calls == 2


def test_graph_and_eval_settings_are_explicit():
    settings = load_settings()
    assert settings.graph.enabled
    assert settings.graph.method == "llm"
    assert settings.graph.source_kinds == ["docs", "sql"]
    assert settings.graph.community_algorithm in {"louvain", "greedy_modularity", "connected_components"}
    assert settings.eval.split == "dev"
    assert settings.retrieval.graph_top_k > 0


def test_graph_artifact_tag_keeps_model_runs_separate(tmp_path: Path):
    from src.branch_sql_MVP.offline import graph

    settings = load_settings()
    paths = settings.paths.model_copy(update={"artifacts": str(tmp_path)})
    settings = settings.model_copy(update={"paths": paths})
    base = {"nodes": [], "edges": [], "parameters": {"model": "gpt"}}
    tagged = {"nodes": [], "edges": [], "parameters": {"model": "gemini"}}
    (tmp_path / "sample.graph.json").write_text(json.dumps(base), encoding="utf-8")
    (tmp_path / "sample.gemini_3_5_flash.graph.json").write_text(
        json.dumps(tagged), encoding="utf-8"
    )

    assert graph.load("sample", settings=settings)["parameters"]["model"] == "gpt"
    assert graph.load(
        "sample", artifact_tag="gemini_3_5_flash", settings=settings
    )["parameters"]["model"] == "gemini"


def test_embed_writes_graph_vectors_separately(tmp_path: Path, monkeypatch):
    from src.branch_sql_MVP.offline import embed

    settings = load_settings()
    paths = settings.paths.model_copy(update={"artifacts": str(tmp_path)})
    settings = settings.model_copy(update={"paths": paths})
    (tmp_path / "sample.graph.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(embed, "load_chunks", lambda *_args, **_kwargs: [{"id": "chunk", "text": "chunk"}])
    monkeypatch.setattr(
        embed.graph,
        "embedding_items",
        lambda *_args, **_kwargs: [{"id": "entity", "kind": "graph_entity", "text": "entity"}],
    )
    monkeypatch.setattr(
        embed,
        "encode",
        lambda items, _cfg: [{"id": item["id"], "dense": [1.0, 0.0], "sparse": {"indices": [1], "values": [1.0]}} for item in items],
    )

    result = embed.run("sample", settings=settings)

    assert result["vectors"] == 1
    assert result["graph_vectors"] == 1
    row = json.loads((tmp_path / "sample.graph_vectors.jsonl").read_text(encoding="utf-8"))
    assert row["id"] == "entity"
    assert row["kind"] == "graph_entity"


def test_index_routes_graph_points_to_graph_collection(tmp_path: Path, monkeypatch):
    from src.branch_sql_MVP.offline import index

    settings = load_settings()
    paths = settings.paths.model_copy(update={"artifacts": str(tmp_path)})
    settings = settings.model_copy(update={"paths": paths})
    (tmp_path / "sample.parents.jsonl").write_text(
        json.dumps({"id": "parent", "text": "parent"}) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(index, "load_chunks", lambda *_args, **_kwargs: [{
        "id": "chunk", "parent_id": "parent", "text": "chunk", "type": "text", "source": "sample.md",
    }])
    monkeypatch.setattr(index, "load_vectors", lambda *_args, **_kwargs: [{
        "id": "chunk", "dense": [1.0, 0.0], "sparse": {"indices": [1], "values": [1.0]},
    }])
    monkeypatch.setattr(index, "load_graph_vectors", lambda *_args, **_kwargs: [{
        "id": "entity", "kind": "graph_entity", "dense": [0.0, 1.0], "sparse": {"indices": [2], "values": [1.0]},
    }])
    monkeypatch.setattr(index.graph, "embedding_items", lambda *_args, **_kwargs: [{
        "id": "entity", "kind": "graph_entity", "text": "table: ORDERS", "metadata": {"name": "ORDERS"},
    }])

    class FakeQdrant:
        def __init__(self):
            self.collections = []
            self.points = []

        def upsert(self, collection, **kwargs):
            self.collections.append(collection)
            self.points.extend(kwargs["points"])

    qdrant = FakeQdrant()
    monkeypatch.setattr(index, "client", lambda _settings: qdrant)
    monkeypatch.setattr(index, "ensure_collection", lambda *_args, **_kwargs: True)

    result = index.run("sample", kind="docs", knowledge_id="p1", settings=settings)

    assert result["points"] == 1
    assert result["graph_points"] == 1
    assert qdrant.collections == ["sqlp1__docs", "sqlp1__graph"]
    assert str(qdrant.points[-1].id) == str(uuid.uuid5(index.NAMESPACE, "graph:sample:entity"))

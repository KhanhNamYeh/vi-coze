from __future__ import annotations

import sqlite3
from pathlib import Path

from src.branch_sql_MVP.data.catalog import load_benchmark_cases
from src.branch_sql_MVP.offline.event_index import build_event_index
from src.branch_sql_MVP.offline.schema_catalog import build_schema_catalog, write_schema_catalog
from src.branch_sql_MVP.online.llm import RouteDecisionOutput
from src.branch_sql_MVP.online.sag_retrieval import expand_event_neighborhood
from src.branch_sql_MVP.online.sql_execution import execute_readonly_sql
from src.branch_sql_MVP.pipeline.contracts import SQLPrediction
from src.branch_sql_MVP.pipeline.execution_repair import build_repair_workflow
from src.branch_sql_MVP.pipeline.prompt_baseline import build_prompt_workflow
from src.branch_sql_MVP.settings import load_settings


def _database(tmp_path: Path) -> Path:
    path = tmp_path / "tiny.sqlite"
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            CREATE TABLE parent(id INTEGER PRIMARY KEY, name TEXT);
            CREATE TABLE child(id INTEGER PRIMARY KEY, parent_id INTEGER REFERENCES parent(id));
            INSERT INTO parent VALUES (1, 'một');
            INSERT INTO child VALUES (10, 1);
            """
        )
    return path


def test_benchmark_payload_never_contains_gold() -> None:
    settings = load_settings()
    case = load_benchmark_cases(settings.path(settings.paths.dev), "dev")[0]
    payload = case.workflow_input()
    assert "gold_sql" not in payload
    assert "SQL" not in payload
    assert case.stable_id.startswith("vi:dev:")


def test_readonly_execution_accepts_cte_and_rejects_write(tmp_path: Path) -> None:
    database = _database(tmp_path)
    good = execute_readonly_sql(
        database,
        "WITH RECURSIVE n(x) AS (SELECT 1 UNION ALL SELECT x+1 FROM n WHERE x<5) SELECT max(x) FROM n",
    )
    denied = execute_readonly_sql(database, "DELETE FROM parent")
    assert good.status == "success"
    assert good.preview == [[5]]
    assert denied.status == "policy_violation"


def test_schema_and_event_artifacts_have_provenance_and_bounds(tmp_path: Path) -> None:
    database = _database(tmp_path)
    business = tmp_path / "tiny.md"
    business.write_text("## Quy tắc\nchild.parent_id nối với parent.id.\n", encoding="utf-8")
    catalog = build_schema_catalog(database, value_limit=2)
    event_index = build_event_index(catalog, business)
    seeds = [event_index["events"][0]["id"]]
    expanded = expand_event_neighborhood(seeds, event_index, hops=1, node_budget=2, token_budget=100)
    assert catalog["fingerprint"]
    assert any(table["foreign_keys"] for table in catalog["tables"])
    assert event_index["schema_fingerprint"] == catalog["fingerprint"]
    assert all(event["source"] for event in event_index["events"])
    assert 1 <= len(expanded) <= 2


def test_prompt_langgraph_has_checkpointed_unique_thread(monkeypatch, tmp_path: Path) -> None:
    database = _database(tmp_path)
    business = tmp_path / "tiny.md"
    business.write_text("Bảng parent lưu cha mẹ.", encoding="utf-8")
    schema = write_schema_catalog(build_schema_catalog(database), tmp_path / "schema.json")

    monkeypatch.setattr(
        "src.branch_sql_MVP.pipeline.prompt_baseline.generate_sql_candidate",
        lambda *args, **kwargs: SQLPrediction(sql="SELECT COUNT(*) FROM parent", confidence=0.9),
    )
    graph = build_prompt_workflow(load_settings())
    result = graph.invoke(
        {
            "stable_id": "case-1",
            "question": "Có bao nhiêu?",
            "database_path": str(database),
            "schema_catalog_path": str(schema),
            "business_path": str(business),
            "candidates": [],
            "trajectory": [],
        },
        {"configurable": {"thread_id": "test:case-1"}},
    )
    assert result["final_prediction"]["sql"] == "SELECT COUNT(*) FROM parent;"
    assert [step["node"] for step in result["trajectory"]] == [
        "assemble_full_context",
        "generate_one_candidate",
    ]


def test_repair_langgraph_stops_after_success(monkeypatch, tmp_path: Path) -> None:
    database = _database(tmp_path)
    calls = iter(
        [
            SQLPrediction(sql="SELECT missing FROM parent", confidence=0.2),
            SQLPrediction(sql="SELECT COUNT(*) FROM parent", confidence=0.9),
        ]
    )
    monkeypatch.setattr(
        "src.branch_sql_MVP.pipeline.execution_repair.build_linked_context",
        lambda *args, **kwargs: ("context", [], []),
    )
    monkeypatch.setattr(
        "src.branch_sql_MVP.pipeline.execution_repair.generate_sql_candidate",
        lambda *args, **kwargs: next(calls),
    )
    monkeypatch.setattr(
        "src.branch_sql_MVP.pipeline.execution_repair.repair_sql_candidate",
        lambda *args, **kwargs: next(calls),
    )
    graph = build_repair_workflow(load_settings())
    result = graph.invoke(
        {
            "stable_id": "case-2",
            "question": "Có bao nhiêu?",
            "database_path": str(database),
            "schema_catalog_path": str(tmp_path / "unused.json"),
            "event_index_path": str(tmp_path / "unused-events.json"),
            "context_parameters": {
                "knowledge_id": "test",
                "doc_id": "test",
                "use_relational_context": False,
            },
            "max_repairs": 2,
            "candidates": [],
            "observations": [],
            "trajectory": [],
        },
        {"configurable": {"thread_id": "test:case-2"}},
    )
    assert result["repair_count"] == 1
    assert result["final_prediction"]["sql"] == "SELECT COUNT(*) FROM parent;"
    assert [item["status"] for item in result["observations"]] == ["missing_object", "success"]


def test_repair_langgraph_honors_disabled_contextual_selector(monkeypatch, tmp_path: Path) -> None:
    database = _database(tmp_path)
    item = {"id": "schema:parent", "kind": "schema", "text": "parent(id)", "source": "test"}
    monkeypatch.setattr(
        "src.branch_sql_MVP.pipeline.execution_repair.build_linked_context",
        lambda *args, **kwargs: ("context", [item], []),
    )
    monkeypatch.setattr("src.branch_sql_MVP.pipeline.execution_repair.load_event_index", lambda *args: {})
    monkeypatch.setattr("src.branch_sql_MVP.pipeline.execution_repair.retrieve_seed_events", lambda *args, **kwargs: [])
    monkeypatch.setattr("src.branch_sql_MVP.pipeline.execution_repair.expand_event_neighborhood", lambda *args, **kwargs: [])
    monkeypatch.setattr(
        "src.branch_sql_MVP.pipeline.execution_repair.select_contextual_evidence",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("selector must be skipped")),
    )
    monkeypatch.setattr(
        "src.branch_sql_MVP.pipeline.execution_repair.generate_sql_candidate",
        lambda *args, **kwargs: SQLPrediction(sql="SELECT COUNT(*) FROM parent", confidence=0.9),
    )
    graph = build_repair_workflow(load_settings())
    result = graph.invoke(
        {
            "stable_id": "case-selector-off",
            "question": "Có bao nhiêu?",
            "database_path": str(database),
            "schema_catalog_path": str(tmp_path / "unused.json"),
            "event_index_path": str(tmp_path / "unused-events.json"),
            "context_parameters": {
                "knowledge_id": "test",
                "doc_id": "test",
                "contextual_selector": False,
                "token_budget": 100,
            },
            "max_repairs": 0,
            "candidates": [],
            "observations": [],
            "trajectory": [],
        },
        {"configurable": {"thread_id": "test:selector-off"}},
    )
    assert result["final_prediction"]["sql"] == "SELECT COUNT(*) FROM parent;"
    assert result["trajectory"][0]["selector"]["mode"] == "deterministic_budget"


def test_adaptive_langgraph_fans_out_and_fans_in(monkeypatch, tmp_path: Path) -> None:
    from src.branch_sql_MVP.pipeline.adaptive_workflow import build_adaptive_workflow

    database = _database(tmp_path)
    business = tmp_path / "tiny.md"
    business.write_text("Bảng parent lưu cha mẹ.", encoding="utf-8")
    schema = write_schema_catalog(build_schema_catalog(database), tmp_path / "schema.json")
    monkeypatch.setattr(
        "src.branch_sql_MVP.pipeline.adaptive_workflow.decide_workflow_route",
        lambda *args, **kwargs: (
            RouteDecisionOutput(route="full", candidate_count=2, reason="test"),
            {"input_tokens": 0, "output_tokens": 0},
        ),
    )
    monkeypatch.setattr(
        "src.branch_sql_MVP.pipeline.adaptive_workflow.generate_sql_candidate",
        lambda *args, **kwargs: SQLPrediction(sql="SELECT COUNT(*) FROM parent", confidence=0.9),
    )
    monkeypatch.setattr(
        "src.branch_sql_MVP.pipeline.adaptive_workflow.select_candidate_with_model",
        lambda *args, **kwargs: ("candidate_1", {"reason": "test"}),
    )
    graph = build_adaptive_workflow(load_settings())
    result = graph.invoke(
        {
            "stable_id": "case-3",
            "question": "Có bao nhiêu?",
            "difficulty": "simple",
            "database_path": str(database),
            "schema_catalog_path": str(schema),
            "business_path": str(business),
            "route_parameters": {"max_candidates": 2},
            "candidates": [],
            "observations": [],
            "trajectory": [],
        },
        {"configurable": {"thread_id": "test:case-3"}},
    )
    assert result["route"] == "full"
    assert len(result["candidates"]) == 2
    assert len(result["observations"]) == 2
    assert result["final_prediction"]["sql"] == "SELECT COUNT(*) FROM parent;"

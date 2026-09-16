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


def test_prompt_langgraph_has_checkpointed_unique_thread(monkeypatch, tmp_path):
    from src.branch_sql_MVP.tests.test_studio import install_model
    database = _database(tmp_path)
    business = tmp_path / "tiny.md"
    business.write_text("parent table", encoding="utf-8")
    schema = write_schema_catalog(build_schema_catalog(database), tmp_path / "schema.json")
    install_model(monkeypatch, lambda *a, **k: SQLPrediction(sql="SELECT COUNT(*) FROM parent", confidence=.9))
    graph = build_prompt_workflow(load_settings())
    config={"configurable":{"thread_id":"case-1"}}
    result=graph.invoke({"question":"count?","database_path":str(database),"schema_catalog_path":str(schema),"business_path":str(business)},config)
    assert result["final_prediction"]["sql"] == "SELECT COUNT(*) FROM parent;"
    assert graph.get_state(config).values == result
    assert len(result["candidates"]) == 1
    assert any(row["node"] == "generate" for row in result["trajectory"])


def test_repair_langgraph_stops_after_success(monkeypatch, tmp_path):
    from src.branch_sql_MVP.tests.test_studio import install_model
    database=_database(tmp_path)
    schema=tmp_path/"schema.json"
    write_schema_catalog(build_schema_catalog(database),schema)
    monkeypatch.setattr("src.branch_sql_MVP.online.context_builder.retrieve_hybrid_evidence",lambda *a,**k:[])
    calls=iter([SQLPrediction(sql="SELECT missing FROM parent",confidence=.2),SQLPrediction(sql="SELECT COUNT(*) FROM parent",confidence=.9)])
    install_model(monkeypatch,lambda *a,**k:next(calls))
    result=build_repair_workflow(load_settings()).invoke({"question":"count?","database_path":str(database),"schema_catalog_path":str(schema), "context_parameters":{"knowledge_id":"test","doc_id":"test","use_relational_context":False},"max_repairs":2})
    assert result["repair_count"] == 1
    assert result["final_prediction"]["sql"] == "SELECT COUNT(*) FROM parent;"
    assert [o["status"] for o in result["observations"]] == ["missing_object","success"]


def test_repair_langgraph_honors_disabled_contextual_selector(monkeypatch,tmp_path):
    from src.branch_sql_MVP.tests.test_studio import install_model
    database=_database(tmp_path)
    item={"id":"schema:parent","kind":"schema","text":"parent(id)","source":"test"}
    schema=tmp_path/"schema.json"
    write_schema_catalog(build_schema_catalog(database),schema)
    monkeypatch.setattr("src.branch_sql_MVP.online.context_builder.retrieve_hybrid_evidence",lambda *a,**k:[])
    monkeypatch.setattr("src.branch_sql_MVP.workflow.nodes.domain.load_event_index",lambda *a:{})
    monkeypatch.setattr("src.branch_sql_MVP.workflow.nodes.domain.retrieve_seed_events",lambda *a,**k:[])
    monkeypatch.setattr("src.branch_sql_MVP.workflow.nodes.domain.expand_event_neighborhood",lambda *a,**k:[])
    calls=[]
    def generate(*a,**k):
        calls.append(a)
        return SQLPrediction(sql="SELECT COUNT(*) FROM parent",confidence=.9)
    install_model(monkeypatch,generate)
    result=build_repair_workflow(load_settings()).invoke({"question":"count?","database_path":str(database),"schema_catalog_path":str(schema),"event_index_path":"unused", "context_parameters":{"knowledge_id":"test","doc_id":"test","contextual_selector":False,"token_budget":100},"max_repairs":0})
    assert result["final_prediction"]["sql"] == "SELECT COUNT(*) FROM parent;"
    assert len(calls)==1
    assert "selector" not in result["node_outputs"]


def test_adaptive_langgraph_fans_out_and_fans_in(monkeypatch,tmp_path):
    # Exercise the same compiler used by both the Studio and compatibility wrapper.
    from src.branch_sql_MVP.tests.test_workflow_templates import test_adaptive_three_candidates_and_invalid_choice
    test_adaptive_three_candidates_and_invalid_choice(tmp_path)


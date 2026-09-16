from pathlib import Path

import pytest

from src.branch_sql_MVP.workflow.compiler import compile_workflow
from src.branch_sql_MVP.workflow.contracts import Edge, NodeInstance, Reference, WorkflowDefinition
from src.branch_sql_MVP.workflow.registry import node_type_metadata
from src.branch_sql_MVP.workflow.store import load_workflow, save_workflow
from src.branch_sql_MVP.workflow.nodes.llm import render_prompt
from src.branch_sql_MVP.workflow.templates import templates
from src.branch_sql_MVP.app import studio
from fastapi import FastAPI
from fastapi.testclient import TestClient
from unittest.mock import patch
from types import SimpleNamespace
from src.branch_sql_MVP.workflow.nodes.llm import invoke_llm
from src.branch_sql_MVP.workflow.registry import _context, _retrieval


def test_shared_type_instances_compile_and_keep_outputs_separate(tmp_path: Path):
    workflow = WorkflowDefinition(
        id="shared_llm_contract",
        kind="online",
        nodes=[
            NodeInstance(id="start", type="start", label="Start"),
            NodeInstance(id="one", type="passthrough", label="One", config={"value": "a"}),
            NodeInstance(id="two", type="passthrough", label="Two", config={"value": "b"}),
        ],
        edges=[Edge(source="start", target="one"), Edge(source="start", target="two")],
    )
    result = compile_workflow(workflow).invoke({"node_outputs": {}})
    assert result["node_outputs"]["one"]["value"] == "a"
    assert result["node_outputs"]["two"]["value"] == "b"
    saved = save_workflow(tmp_path, workflow)
    assert load_workflow(tmp_path, workflow.id).revision == saved.revision


def test_contract_rejects_bad_reference_and_unknown_type():
    with pytest.raises(ValueError):
        WorkflowDefinition(id="bad", kind="online", nodes=[NodeInstance(id="a", type="passthrough", label="A", inputs={"x": Reference(node_id="missing", output="value")})])
    assert any(item["type"] == "llm" for item in node_type_metadata())
    with pytest.raises(ValueError, match="bounded-loop"):
        WorkflowDefinition.model_validate({"id": "cycle", "kind": "online", "nodes": [
            {"id": "a", "type": "passthrough", "label": "A"},
            {"id": "b", "type": "passthrough", "label": "B"},
        ], "edges": [{"source": "a", "target": "b"}, {"source": "b", "target": "a"}]})


def test_shared_llm_prompt_resolves_variables_without_eval():
    assert render_prompt("Q={{question}} SQL={{candidate.sql}}", {"question": "tổng", "candidate": {"sql": "SELECT 1"}}) == "Q=tổng SQL=SELECT 1"
    with pytest.raises(ValueError, match="thiếu biến prompt"):
        render_prompt("{{missing}}", {})


def test_studio_exposes_shared_node_library_and_workflow_revision(tmp_path, monkeypatch):
    monkeypatch.setattr(studio, "WORKFLOW_ROOT", tmp_path)
    client = TestClient(FastAPI())
    client.app.include_router(studio.router)
    assert any(item["type"] == "llm" for item in client.get("/studio/node-types").json())
    payload = {"id": "demo", "kind": "online", "revision": 1, "nodes": [{"id": "a", "type": "passthrough", "label": "A", "config": {"value": 1}}], "edges": [], "outputs": {"answer": {"node_id": "a", "output": "value"}}}
    created = client.post("/studio/workflows", json=payload)
    assert created.status_code == 200
    assert client.get("/studio/workflows/demo").json()["revision"] == 1
    ran = client.post("/studio/workflows/demo/run", json={"inputs": {}})
    assert ran.status_code == 200
    assert ran.json()["node_outputs"]["a"]["value"] == 1
    assert ran.json()["outputs"] == {"answer": 1}
    assert len(templates()) == 8
    assert all(any(node.type == "llm" for node in item.nodes) for item in templates())


def test_condition_executes_only_selected_edge_and_unimplemented_node_fails():
    workflow = WorkflowDefinition.model_validate({"id": "branch_check", "kind": "online", "nodes": [
        {"id": "start", "type": "start", "label": "Start"},
        {"id": "condition", "type": "condition", "label": "Condition", "config": {"route": "yes"}},
        {"id": "yes", "type": "passthrough", "label": "Yes", "config": {"value": "Y"}},
        {"id": "no", "type": "passthrough", "label": "No", "config": {"value": "N"}},
    ], "edges": [
        {"source": "start", "target": "condition"},
        {"source": "condition", "target": "yes", "condition": "yes"},
        {"source": "condition", "target": "no", "condition": "no"},
    ]})
    outputs = compile_workflow(workflow).invoke({"node_outputs": {}})["node_outputs"]
    assert "yes" in outputs and "no" not in outputs
    incomplete = WorkflowDefinition.model_validate({"id": "incomplete", "kind": "online", "nodes": [{"id": "sql", "type": "sql_executor", "label": "SQL"}]})
    with pytest.raises(ValueError, match="database và sql"):
        compile_workflow(incomplete).invoke({"node_outputs": {}})


def test_llm_schema_is_enforced_and_workflow_rejects_secret():
    with pytest.raises(ValueError, match="secret"):
        WorkflowDefinition.model_validate({"id": "secret", "kind": "online", "nodes": [{"id": "llm", "type": "llm", "label": "LLM", "config": {"user_prompt": "x", "api_key": "dummy"}}]})
    fake = SimpleNamespace(invoke=lambda _: SimpleNamespace(content="{}", usage_metadata={}))
    with patch("src.branch_sql_MVP.workflow.nodes.llm.build_model", return_value=fake), pytest.raises(ValueError, match="output_schema"):
        invoke_llm({}, {"user_prompt": "x", "response_format": "json", "output_schema": {"type": "object", "required": ["sql"], "properties": {"sql": {"type": "string"}}}})


def test_workflow_config_allows_token_limits_but_rejects_default_secret():
    workflow = WorkflowDefinition.model_validate({
        "id": "token_limits", "kind": "online",
        "nodes": [{"id": "llm", "type": "llm", "label": "LLM", "config": {"user_prompt": "x", "max_tokens": 1000, "token_budget": 5000, "tokenizer_model": "demo"}}],
    })
    assert workflow.nodes[0].config["max_tokens"] == 1000
    with pytest.raises(ValueError, match="secret"):
        WorkflowDefinition.model_validate({
            "id": "default_secret", "kind": "online",
            "nodes": [{"id": "a", "type": "passthrough", "label": "A"}],
            "defaults": {"api_key": "must-not-persist"},
        })


def test_nested_output_references_and_real_node_adapters():
    workflow = WorkflowDefinition.model_validate({"id": "nested_ref", "kind": "online", "nodes": [
        {"id": "source", "type": "passthrough", "label": "Source", "config": {"value": {"sql": "SELECT 1"}}},
        {"id": "target", "type": "passthrough", "label": "Target", "inputs": {"value": {"node_id": "source", "output": "value.sql"}}},
    ], "edges": [{"source": "source", "target": "target"}]})
    assert compile_workflow(workflow).invoke({"inputs": {}, "node_outputs": {}})["node_outputs"]["target"]["value"] == "SELECT 1"
    assert _context({"context": "trusted context"}, {"mode": "direct"})["text"] == "trusted context"
    with pytest.raises(ValueError, match="retrieval cần"):
        _retrieval({}, {})
    with patch("src.branch_sql_MVP.online.retrieval.retrieve", return_value=[{"text": "hit"}]) as retrieve:
        output = _retrieval({"question": "doanh thu"}, {"kind": "docs", "knowledge_id": "demo"})
    retrieve.assert_called_once()
    assert output["items"] == [{"text": "hit"}]


def test_editor_templates_pass_the_explicit_context_input():
    context = next(node for node in templates()[0].nodes if node.id == "context")
    assert context.config["mode"] == "full"
    assert context.inputs["schema_catalog_path"].output == "schema_catalog_path"

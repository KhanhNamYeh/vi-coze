"""API xem đồ thị thật, phát lại benchmark và chạy cấu hình đã tối ưu."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from time import perf_counter
from uuid import uuid4
from typing import Literal

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

from ..settings import ROOT, LLMSettings, RetrievalSettings, load_settings

router = APIRouter()
from .workflow_api import router as workflow_router
router.include_router(workflow_router)
BUNDLE = ROOT / ".runtime/luna_test_optimization_20260908/bundle.json"
WORKFLOW_ROOT = ROOT / ".runtime/studio/workflows"


@router.get("/studio/node-types")
def node_types():
    """Return the reusable node library used by the workflow editor."""
    from ..workflow.registry import node_type_metadata
    return node_type_metadata()


@router.get("/studio/workflow-templates")
def workflow_templates():
    from ..workflow.templates import templates
    return [item.model_dump(mode="json") for item in templates()]


@router.post("/studio/llm/preview")
def llm_preview(request: dict):
    from ..workflow.nodes.llm import preview_prompt
    try:
        return preview_prompt(request.get("inputs", {}), request.get("config", {}))
    except (KeyError, ValueError) as error:
        raise HTTPException(422, str(error)) from error


@router.get("/studio/workflows")
def workflows():
    from ..workflow.store import list_workflows
    return [item.model_dump(mode="json") for item in list_workflows(WORKFLOW_ROOT)]


@router.post("/studio/workflows")
def create_workflow(definition: dict):
    from ..workflow.contracts import WorkflowDefinition
    from ..workflow.store import save_workflow
    from ..workflow.compiler import compile_workflow
    try:
        item = WorkflowDefinition.model_validate(definition)
        compile_workflow(item)
        return save_workflow(WORKFLOW_ROOT, item).model_dump(mode="json")
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


@router.get("/studio/workflows/{workflow_id}")
def get_workflow(workflow_id: str):
    from ..workflow.store import load_workflow
    try:
        return load_workflow(WORKFLOW_ROOT, workflow_id).model_dump(mode="json")
    except FileNotFoundError as error:
        raise HTTPException(404, "Không tìm thấy workflow") from error


@router.put("/studio/workflows/{workflow_id}")
def update_workflow(workflow_id: str, definition: dict):
    from ..workflow.contracts import WorkflowDefinition
    from ..workflow.store import save_workflow
    if definition.get("id") != workflow_id:
        raise HTTPException(422, "workflow id không khớp URL")
    try:
        item = WorkflowDefinition.model_validate(definition)
        from ..workflow.compiler import compile_workflow
        compile_workflow(item)
        return save_workflow(WORKFLOW_ROOT, item, expected_revision=item.revision).model_dump(mode="json")
    except FileNotFoundError as error:
        raise HTTPException(404, "Không tìm thấy workflow") from error
    except ValueError as error:
        raise HTTPException(409, str(error)) from error


@router.post("/studio/workflows/{workflow_id}/run")
def run_saved_workflow(workflow_id: str, request: dict | None = None):
    """Execute the saved definition through the shared LangGraph compiler."""
    from ..workflow.compiler import compile_workflow, resolve_workflow_outputs
    from ..workflow.store import load_workflow
    try:
        definition = load_workflow(WORKFLOW_ROOT, workflow_id)
    except FileNotFoundError as error:
        raise HTTPException(404, "Không tìm thấy workflow") from error
    try:
        result = compile_workflow(definition).invoke({"inputs": (request or {}).get("inputs", {}), "node_outputs": {}})
        node_outputs = result.get("node_outputs", {})
        return {"workflow_id": workflow_id, "revision": definition.revision,
                "node_outputs": node_outputs,
                "outputs": resolve_workflow_outputs(definition, node_outputs)}
    except (ValueError, RuntimeError, KeyError) as error:
        raise HTTPException(422, str(error)) from error


def bundle():
    return json.loads(BUNDLE.read_text(encoding="utf-8")) if BUNDLE.is_file() else {"selected": [], "test_ids": []}


def selected(pipeline_id: str):
    app = load_settings()
    presets = json.loads((ROOT / "pipeline/presets.json").read_text(encoding="utf-8"))
    for row in presets:
        if row["id"] == pipeline_id:
            return {"scenario": row["scenario"],
                    "requires_index": row.get("requires_index", row["scenario"] != "P1"),
                    "manifest": {
                "model_provider": app.api.provider, "model": app.api.model,
                "parameters": {**row["parameters"], "generation": app.llm.model_dump()}}}
    raise HTTPException(404, "Không tìm thấy pipeline")


def runtime(item, *, provider=None, model=None):
    app = load_settings()
    parameters = item["manifest"]["parameters"]
    provider = provider or app.api.provider
    model = model or app.api.model
    if provider not in app.api.providers:
        raise HTTPException(422, "Provider chưa được khai báo")
    generation = dict(parameters["generation"])
    if (provider, model) != (item["manifest"]["model_provider"], item["manifest"]["model"]):
        # Provider-specific options from the old benchmark must not reach a different model.
        generation["extra"] = app.llm.extra
    app = app.model_copy(update={"api": app.api.model_copy(update={"provider": provider, "model": model})})
    retrieval = app.retrieval.model_dump()
    retrieval.update({k: v for k, v in parameters["context"].items() if k in retrieval})
    return app.model_copy(update={"retrieval": RetrievalSettings.model_validate(retrieval),
                                  "llm": LLMSettings.model_validate(generation)})


@router.get("/", include_in_schema=False)
def studio():
    return FileResponse(Path(__file__).with_name("static") / "workspace.html")


@router.get("/studio/assets/{name}", include_in_schema=False)
def workspace_asset(name: str):
    if name not in {"workspace.js", "workspace.css"}:
        raise HTTPException(404, "Unknown asset")
    return FileResponse(Path(__file__).with_name("static") / name)


@router.post("/studio/datasets/import")
async def import_studio_dataset(name: str = Form(...), question: str = Form("Liệt kê dữ liệu."), database: UploadFile = File(...), business: UploadFile = File(...), index: bool = Form(False)):
    """Import a user SQLite + business document into the shared dataset registry."""
    from ..data.import_dataset import import_dataset
    if Path(database.filename or "").suffix.lower() not in {".sqlite", ".db"}:
        raise HTTPException(422, "database phải là file SQLite .sqlite hoặc .db")
    suffix = Path(business.filename or "").suffix.lower()
    if suffix not in {".md", ".docx", ".pdf", ".xlsx"}:
        raise HTTPException(422, "business hỗ trợ .md, .docx, .pdf hoặc .xlsx")
    staging = ROOT / ".runtime/studio/staging" / uuid4().hex
    staging.mkdir(parents=True, exist_ok=False)
    db_path = staging / ("source" + Path(database.filename or "database.sqlite").suffix.lower())
    business_path = staging / ("business" + suffix)
    try:
        with db_path.open("wb") as target:
            shutil.copyfileobj(database.file, target)
        with business_path.open("wb") as target:
            shutil.copyfileobj(business.file, target)
        return import_dataset(name, db_path, business_path, question=question, build_index=index)
    except FileExistsError as error:
        raise HTTPException(409, str(error)) from error
    except (ValueError, FileNotFoundError) as error:
        raise HTTPException(422, str(error)) from error
    finally:
        shutil.rmtree(staging, ignore_errors=True)


@router.get("/studio/pipelines")
def pipelines():
    app = load_settings()
    return [{"id": row["id"], "scenario": row["scenario"], "metrics": {},
             "parameters": row["parameters"], "model": app.api.model}
            for row in json.loads((ROOT / "pipeline/presets.json").read_text(encoding="utf-8"))]


@router.get("/studio/pipelines/{pipeline_id}/graph")
def graph_definition(pipeline_id: str):
    from ..pipeline.registry import build_workflow

    item = selected(pipeline_id)
    graph = build_workflow(item["scenario"], runtime(item)).get_graph()
    return {"nodes": [{"id": key} for key in graph.nodes],
            "edges": [{"source": edge.source, "target": edge.target,
                       "conditional": edge.conditional, "label": str(edge.data or "")}
                      for edge in graph.edges]}


@router.get("/studio/cases")
def cases():
    from ..data.catalog import load_benchmark_cases

    from ..data.import_dataset import datasets
    result = [{"id": "dataset:" + row["id"], "question": row["question"],
               "database": row["id"], "difficulty": "unknown", "indexed": row["indexed"]}
              for row in datasets()]
    ids = set(bundle()["test_ids"])
    app = load_settings()
    if ids and (app.path(app.paths.dev) / "dev.json").is_file():
        result += [{"id": case.stable_id, "question": case.question, "database": case.db_id,
                    "difficulty": case.difficulty}
                   for case in load_benchmark_cases(app.path(app.paths.dev), "dev") if case.stable_id in ids]
    return result


@router.get("/studio/pipelines/{pipeline_id}/replay/{case_id}")
def replay(pipeline_id: str, case_id: str):
    item = next((row for row in bundle()["selected"] if
                 row.get("scenario_name", row["config"]["name"].removesuffix("-alternative")) == pipeline_id), None)
    if item is None or case_id.startswith("dataset:"):
        raise HTTPException(404, "Dataset mới chưa có lịch sử benchmark; dùng Chạy thử.")
    path = BUNDLE.parent / "runs" / item["run_id"] / "cases.jsonl"
    for line in reversed(path.read_text(encoding="utf-8").splitlines()):
        row = json.loads(line)
        if row["stable_id"] == case_id:
            return {key: row.get(key) for key in ["stable_id", "prediction", "trajectory", "candidates",
                                                  "observations", "route", "repair_count", "run_error"]}
    raise HTTPException(404, "Chưa có trace đã lưu cho câu hỏi này")


class RunRequest(BaseModel):
    pipeline_id: str
    case_id: str
    question: str | None = Field(None, min_length=1, max_length=20000)
    provider: str | None = None
    model: str | None = None
    api_key: str | None = None
    mode: Literal["sql_only", "answer"] = "sql_only"


@router.post("/studio/run")
def run(request: RunRequest):
    from ..data.catalog import load_benchmark_cases
    from ..pipeline.registry import build_workflow

    item = selected(request.pipeline_id)
    app = runtime(item, provider=request.provider, model=request.model)
    parameters = item["manifest"]["parameters"]
    if request.case_id.startswith("dataset:"):
        from ..data.import_dataset import datasets, dataset_settings, workspace
        name = request.case_id.removeprefix("dataset:")
        record = next((row for row in datasets() if row["id"] == name), None)
        if record is None:
            raise HTTPException(404, "Dataset chưa được import")
        if item["requires_index"] and not record["indexed"]:
            raise HTTPException(422, "Dataset chưa có vector index. Import tên mới với --index để chạy pipeline này.")
        app = dataset_settings(record, app)
        folder = workspace() / name
        state = {"stable_id": request.case_id, "db_id": name, "question": request.question or record["question"],
                 "evidence": "", "difficulty": "unknown", "database_path": str(folder / "database.sqlite"),
                 "business_path": str(folder / "business.md"), "schema_catalog_path": str(folder / "schema.json"),
                 "event_index_path": str(folder / "events.json"),
                 "context_parameters": {**parameters["context"], "knowledge_id": record["knowledge_id"],
                                        "doc_id": record["doc_id"]},
                 "execution_parameters": parameters["execution"], "route_parameters": parameters["route"],
                 "max_repairs": parameters["max_repairs"], "trajectory": [], "candidates": [], "observations": []}
    else:
        if not BUNDLE.is_file() or not (app.path(app.paths.dev) / "dev.json").is_file():
            raise HTTPException(404, "Không tìm thấy dataset; import dữ liệu trước khi chạy.")
        case = next((case for case in load_benchmark_cases(app.path(app.paths.dev), "dev")
                     if case.stable_id == request.case_id), None)
        if case is None:
            raise HTTPException(404, "Không tìm thấy câu hỏi")
        artifacts = bundle()["artifacts"]
        key = f"{case.split}:{case.db_id}"
        parameters = item["manifest"]["parameters"]
        state = {**case.workflow_input(database=Path(artifacts["database_paths"][key])),
                 "scenario": item["scenario"], "schema_catalog_path": artifacts["schema_paths"][key],
                 "event_index_path": artifacts["event_paths"][key],
                 "context_parameters": {**parameters["context"], "knowledge_id": artifacts["knowledge_id"],
                                        "doc_id": artifacts["doc_ids"][key]},
                 "execution_parameters": parameters["execution"], "route_parameters": parameters["route"],
                 "max_repairs": parameters["max_repairs"], "trajectory": [], "candidates": [], "observations": []}
        if request.question and request.question.strip() != case.question.strip():
            state.update(question=request.question.strip(), evidence="", difficulty="unknown")
        from ..settings import IndexSettings
        knowledge = artifacts["knowledge_id"]
        app = app.model_copy(update={"index": IndexSettings.model_validate({
            **app.index.model_dump(), "local_path": str(ROOT / ".runtime/luna_internal_holdout_v1/qdrant"),
            "knowledge_id": knowledge, "collections": {**app.index.collections, knowledge: {
                "docs": knowledge + "__docs", "sql": knowledge + "__train_examples", "graph": knowledge + "__legacy_graph"}}})})
    state["mode"] = request.mode
    graph = build_workflow(item["scenario"], app, provider=app.api.provider,
                           model=app.api.model, api_key=request.api_key)
    config = {"configurable": {"thread_id": str(uuid4())}, "recursion_limit": 40}

    def events():
        started = perf_counter()
        try:
            for mode, chunk in graph.stream(state, config, stream_mode=["updates", "tasks"]):
                yield json.dumps({"type": mode, "data": chunk, "elapsed": perf_counter() - started},
                                 ensure_ascii=False, default=str) + "\n"
            result = graph.get_state(config).values
            payload = {k: result.get(k) for k in ["final_prediction", "trajectory", "candidates", "observations", "route", "selected_candidate_id"]}
            payload["answer"] = result.get("answer")
            yield json.dumps({"type": "complete", "data": payload},
                             ensure_ascii=False, default=str) + "\n"
        except Exception as error:
            message = str(error)
            if request.api_key:
                message = message.replace(request.api_key, "[redacted]")
            yield json.dumps({"type": "error", "message": message}, ensure_ascii=False) + "\n"

    return StreamingResponse(events(), media_type="application/x-ndjson")

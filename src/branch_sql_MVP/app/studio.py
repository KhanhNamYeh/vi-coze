"""API xem đồ thị thật, phát lại benchmark và chạy cấu hình đã tối ưu."""

from __future__ import annotations

import json
from pathlib import Path
from time import perf_counter
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

from ..settings import ROOT, LLMSettings, RetrievalSettings, load_settings

router = APIRouter()
BUNDLE = ROOT / ".runtime/luna_test_optimization_20260908/bundle.json"


def bundle():
    return json.loads(BUNDLE.read_text(encoding="utf-8"))


def selected(pipeline_id: str):
    for item in bundle()["selected"]:
        if item.get("scenario_name", item["config"]["name"].removesuffix("-alternative")) == pipeline_id:
            return item
    raise HTTPException(404, "Không tìm thấy pipeline")


def runtime(item):
    from ..eval.benchmark import benchmark_settings

    app = load_settings()
    parameters = item["manifest"]["parameters"]
    # The copied index retains the original benchmark collection names.
    app = benchmark_settings(app, qdrant_path=ROOT / ".runtime/luna_internal_holdout_v1/qdrant",
                             knowledge_id=bundle()["artifacts"]["knowledge_id"])
    retrieval = app.retrieval.model_dump()
    retrieval.update({k: v for k, v in parameters["context"].items() if k in retrieval})
    return app.model_copy(update={"retrieval": RetrievalSettings.model_validate(retrieval),
                                  "llm": LLMSettings.model_validate(parameters["generation"])})


@router.get("/", include_in_schema=False)
def studio():
    return FileResponse(Path(__file__).with_name("static") / "studio.html")


@router.get("/studio/pipelines")
def pipelines():
    return [{"id": row.get("scenario_name", row["config"]["name"].removesuffix("-alternative")),
             "scenario": row["scenario"], "metrics": row["metrics"],
             "parameters": row["manifest"]["parameters"], "model": row["manifest"]["model"]}
            for row in bundle()["selected"]]


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

    ids = set(bundle()["test_ids"])
    app = load_settings()
    return [{"id": case.stable_id, "question": case.question, "database": case.db_id,
             "difficulty": case.difficulty}
            for case in load_benchmark_cases(app.path(app.paths.dev), "dev") if case.stable_id in ids]


@router.get("/studio/pipelines/{pipeline_id}/replay/{case_id}")
def replay(pipeline_id: str, case_id: str):
    item = selected(pipeline_id)
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


@router.post("/studio/run")
def run(request: RunRequest):
    from ..data.catalog import load_benchmark_cases
    from ..pipeline.registry import build_workflow

    item = selected(request.pipeline_id)
    app = runtime(item)
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
    graph = build_workflow(item["scenario"], app, provider=request.provider or item["manifest"]["model_provider"],
                           model=request.model or item["manifest"]["model"], api_key=request.api_key)
    config = {"configurable": {"thread_id": str(uuid4())}, "recursion_limit": 40}

    def events():
        started = perf_counter()
        try:
            for mode, chunk in graph.stream(state, config, stream_mode=["updates", "tasks"]):
                yield json.dumps({"type": mode, "data": chunk, "elapsed": perf_counter() - started},
                                 ensure_ascii=False, default=str) + "\n"
            result = graph.get_state(config).values
            yield json.dumps({"type": "complete", "data": {k: result.get(k) for k in
                              ["final_prediction", "trajectory", "candidates", "observations", "route"]}},
                             ensure_ascii=False, default=str) + "\n"
        except Exception as error:
            message = str(error)
            if request.api_key:
                message = message.replace(request.api_key, "[redacted]")
            yield json.dumps({"type": "error", "message": message}, ensure_ascii=False) + "\n"

    return StreamingResponse(events(), media_type="application/x-ndjson")

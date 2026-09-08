"""FastAPI + Gradio UI cho MVP. Chạy: uv run --extra api --extra llm python -m src.branch_sql_MVP.app.app"""

from __future__ import annotations

import json
import time
from collections import Counter
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from ..eval import graph as graph_eval
from ..offline import chunk, embed, extract, graph, index, link, pipeline
from ..online.llm import chat
from ..online.retrieval import retrieve
from ..settings import RetrievalSettings, Settings, load_settings, update_settings

STAGES = ("preprocess", "extract", "link", "chunk", "graph", "embed", "index")


class SourceRequest(BaseModel):
    source: str


class DocumentRequest(BaseModel):
    doc_id: str


class ExtractRequest(BaseModel):
    markdown_path: str


class IndexRequest(DocumentRequest):
    knowledge_id: str
    kind: str
    recreate: bool | None = None


class GraphRequest(DocumentRequest):
    kind: Literal["docs", "sql"] = "docs"
    provider: str | None = None
    model: str | None = None
    api_key: str | None = None


class PipelineRequest(SourceRequest):
    knowledge_id: str
    kind: str
    recreate: bool | None = None
    graph_provider: str | None = None
    graph_model: str | None = None
    graph_api_key: str | None = None


class RetrievalRequest(BaseModel):
    query: str
    knowledge_id: str
    kind: Literal["docs", "sql", "graph"]
    mode: Literal["semantic", "keyword", "hybrid"] | None = None
    semantic_weight: float | None = Field(None, ge=0)
    keyword_weight: float | None = Field(None, ge=0)


class ChatRequest(BaseModel):
    query: str
    knowledge_id: str
    provider: str | None = None
    model: str | None = None
    api_key: str | None = None
    mode: Literal["semantic", "keyword", "hybrid"] | None = None
    semantic_weight: float | None = Field(None, ge=0)
    keyword_weight: float | None = Field(None, ge=0)


class GraphEvalRequest(DocumentRequest):
    knowledge_id: str
    split: Literal["dev", "test"] = "dev"


def _runtime_settings(mode=None, semantic_weight=None, keyword_weight=None) -> Settings:
    settings = load_settings()
    changes = {
        key: value
        for key, value in {
            "mode": mode,
            "semantic_weight": semantic_weight,
            "keyword_weight": keyword_weight,
        }.items()
        if value is not None
    }
    retrieval = RetrievalSettings.model_validate({**settings.retrieval.model_dump(), **changes})
    return settings.model_copy(update={"retrieval": retrieval})


def _call(function, *args, **kwargs):
    try:
        return function(*args, **kwargs)
    except Exception as error:  # FastAPI trả lỗi từng stage, không nuốt traceback server.
        raise HTTPException(status_code=400, detail=str(error)) from error


def list_artifacts(settings: Settings | None = None) -> list[dict]:
    app = settings or load_settings()
    base = app.path(app.paths.artifacts)
    if not base.is_dir():
        return []
    return [
        {"name": path.name, "size": path.stat().st_size, "type": path.suffix.lstrip(".")}
        for path in sorted(base.iterdir())
        if path.is_file()
    ]


def read_artifact(name: str, settings: Settings | None = None, limit: int = 120_000) -> str:
    app = settings or load_settings()
    if Path(name).name != name or name.startswith("."):
        raise ValueError("tên artifact không hợp lệ")
    path = app.path(app.paths.artifacts) / name
    if not path.is_file():
        raise FileNotFoundError(path)
    text = path.read_text(encoding="utf-8", errors="replace")
    return text[:limit] + ("\n\n… truncated …" if len(text) > limit else "")


def document_stats(doc_id: str, settings: Settings | None = None) -> dict:
    app = settings or load_settings()
    base = app.path(app.paths.artifacts)
    markdown_dir = app.path(app.paths.markdown)
    stats: dict[str, Any] = {"doc_id": doc_id}

    markdown = markdown_dir / f"{doc_id}.md"
    if markdown.exists():
        text = markdown.read_text(encoding="utf-8")
        stats["preprocess"] = {"characters": len(text), "lines": len(text.splitlines())}
    extracted = base / f"{doc_id}.extract.json"
    if extracted.exists():
        elements = json.loads(extracted.read_text(encoding="utf-8"))["elements"]
        stats["extract"] = {"elements": len(elements), "types": dict(Counter(item["type"] for item in elements))}
    linked = base / f"{doc_id}.linked.json"
    if linked.exists():
        elements = json.loads(linked.read_text(encoding="utf-8"))["elements"]
        stats["link"] = {
            "elements": len(elements),
            "roots": sum(not item.get("parent_id") for item in elements),
            "with_parent": sum(bool(item.get("parent_id")) for item in elements),
        }
    chunks = base / f"{doc_id}.chunks.jsonl"
    if chunks.exists():
        rows = [json.loads(line) for line in chunks.read_text(encoding="utf-8").splitlines() if line]
        parent_file = base / f"{doc_id}.parents.jsonl"
        parents = len(parent_file.read_text(encoding="utf-8").splitlines()) if parent_file.exists() else 0
        stats["chunk"] = {"children": len(rows), "parents": parents, "types": dict(Counter(row["type"] for row in rows))}
    vectors = base / f"{doc_id}.vectors.jsonl"
    if vectors.exists():
        rows = [json.loads(line) for line in vectors.read_text(encoding="utf-8").splitlines() if line]
        stats["embed"] = {"vectors": len(rows), "dimension": len(rows[0]["dense"]) if rows else 0}
    graph_file = base / f"{doc_id}.graph.json"
    if graph_file.exists():
        graph_data = json.loads(graph_file.read_text(encoding="utf-8"))
        stats["graph"] = graph_data.get("stats", {})
    graph_vectors = base / f"{doc_id}.graph_vectors.jsonl"
    if graph_vectors.exists():
        stats.setdefault("embed", {})["graph_vectors"] = len(graph_vectors.read_text(encoding="utf-8").splitlines())
    return stats


def create_api() -> FastAPI:
    api = FastAPI(title="Branch SQL MVP", version="0.1.0")

    @api.get("/health")
    def health():
        return {"status": "ok"}

    @api.get("/settings")
    def get_settings():
        return load_settings().model_dump(mode="json")

    @api.patch("/settings")
    def patch_settings(patch: dict[str, Any]):
        return _call(update_settings, patch).model_dump(mode="json")

    @api.post("/offline/preprocess")
    def preprocess_stage(request: SourceRequest):
        return _call(pipeline.preprocess, request.source)

    @api.post("/offline/extract")
    def extract_stage(request: ExtractRequest):
        return _call(extract.run, request.markdown_path)

    @api.post("/offline/link")
    def link_stage(request: DocumentRequest):
        return _call(link.run, request.doc_id)

    @api.post("/offline/chunk")
    def chunk_stage(request: DocumentRequest):
        return _call(chunk.run, request.doc_id)

    @api.post("/offline/embed")
    def embed_stage(request: DocumentRequest):
        return _call(embed.run, request.doc_id)

    @api.post("/offline/graph")
    def graph_stage(request: GraphRequest):
        return _call(
            graph.run,
            request.doc_id,
            kind=request.kind,
            provider=request.provider,
            model=request.model,
            api_key=request.api_key,
        )

    @api.get("/offline/graph/{doc_id}")
    def graph_artifact(doc_id: str):
        return _call(graph.load, doc_id)

    @api.post("/offline/index")
    def index_stage(request: IndexRequest):
        return _call(
            index.run,
            request.doc_id,
            kind=request.kind,
            knowledge_id=request.knowledge_id,
            recreate=request.recreate,
        )

    @api.post("/offline/pipeline")
    def pipeline_stage(request: PipelineRequest):
        return _call(
            pipeline.run,
            request.source,
            kind=request.kind,
            knowledge_id=request.knowledge_id,
            recreate=request.recreate,
            graph_provider=request.graph_provider,
            graph_model=request.graph_model,
            graph_api_key=request.graph_api_key,
        )

    @api.get("/offline/artifacts")
    def artifacts():
        return list_artifacts()

    @api.get("/offline/artifacts/{name}")
    def artifact(name: str):
        return {"name": name, "content": _call(read_artifact, name)}

    @api.get("/offline/stats/{doc_id}")
    def stats(doc_id: str):
        return _call(document_stats, doc_id)

    @api.post("/retrieve")
    def retrieval(request: RetrievalRequest):
        settings = _runtime_settings(request.mode, request.semantic_weight, request.keyword_weight)
        return _call(
            retrieve,
            request.query,
            kind=request.kind,
            knowledge_id=request.knowledge_id,
            settings=settings,
        )

    @api.post("/chat")
    def one_shot_chat(request: ChatRequest):
        settings = _runtime_settings(request.mode, request.semantic_weight, request.keyword_weight)
        return _call(
            chat,
            request.query,
            knowledge_id=request.knowledge_id,
            settings=settings,
            provider=request.provider,
            model=request.model,
            api_key=request.api_key,
        )

    @api.post("/eval/graph")
    def evaluate_graph(request: GraphEvalRequest):
        return _call(
            graph_eval.evaluate,
            request.doc_id,
            knowledge_id=request.knowledge_id,
            split=request.split,
        )

    return api


def create_ui():
    import gradio as gr

    settings = load_settings()
    stage_titles = {
        "preprocess": "Document → Markdown",
        "extract": "Markdown → heading / table / text",
        "link": "Attach parent_id",
        "chunk": "Elements → parent / child chunks",
        "graph": "Chunks → entities / relationships / communities",
        "embed": "Chunks + graph → dense + sparse vectors",
        "index": "Vectors → Qdrant",
    }

    def chat_once(message, _history, knowledge_id, provider, model, api_key, mode, semantic_weight, keyword_weight):
        runtime = _runtime_settings(mode, semantic_weight, keyword_weight)
        result = chat(
            message,
            knowledge_id=knowledge_id,
            settings=runtime,
            provider=provider,
            model=model,
            api_key=api_key or None,
        )
        return result["answer"]

    def rows(current: str | None = None, done: set[str] | None = None, error: str | None = None):
        done = done or set()
        output = []
        for number, stage in enumerate(STAGES, 1):
            status = "completed" if stage in done else "running" if stage == current else "waiting"
            detail = error if stage == current and error else stage_titles[stage]
            output.append([f"{number:02d} · {stage}", status, detail])
        return output

    def compact(stage: str, result: dict) -> str:
        if stage == "preprocess":
            return Path(result["path"]).name
        if stage in {"extract", "link"}:
            return f"{len(result['elements'])} elements"
        if stage == "chunk":
            return f"{result['chunks']} children · {result['parents']} parents"
        if stage == "graph":
            if result.get("skipped"):
                return f"skipped · {result['reason']}"
            return f"{result['nodes']} nodes · {result['edges']} edges · {result['communities']} communities"
        if stage == "embed":
            return f"{result['vectors']} chunks + {result.get('graph_vectors', 0)} graph · {result['dimension']} dimensions"
        return f"{result['points']} chunks + {result.get('graph_points', 0)} graph · {result['collection']}"

    def artifact_update(value: str | None = None):
        names = [item["name"] for item in list_artifacts()]
        selected = value if value in names else (names[0] if names else None)
        return gr.update(choices=names, value=selected)

    def run_all(file_path, source_path, knowledge_id, kind, recreate, graph_provider, graph_model, graph_api_key):
        source = file_path or source_path
        completed: set[str] = set()
        logs: list[str] = []
        doc_id = ""
        last_result: dict = {}

        def log(stage: str, message: str):
            logs.append(f"{time.strftime('%H:%M:%S')}  {stage.upper():<10} {message}")

        steps = [
            ("preprocess", lambda: pipeline.preprocess(source)),
            ("extract", lambda: extract.run(last_result["path"])),
            ("link", lambda: link.run(doc_id)),
            ("chunk", lambda: chunk.run(doc_id)),
            ("graph", lambda: graph.run(
                doc_id,
                kind=kind,
                provider=graph_provider or None,
                model=graph_model or None,
                api_key=graph_api_key or None,
            )),
            ("embed", lambda: embed.run(doc_id)),
            ("index", lambda: index.run(
                doc_id,
                kind=kind,
                knowledge_id=knowledge_id,
                recreate=recreate,
            )),
        ]
        for stage, action in steps:
            yield rows(stage, completed), doc_id, document_stats(doc_id) if doc_id else {}, "\n".join(logs), artifact_update()
            started = time.perf_counter()
            try:
                last_result = action()
                if stage == "preprocess":
                    doc_id = last_result["doc_id"]
                elapsed = time.perf_counter() - started
                completed.add(stage)
                log(stage, f"OK · {compact(stage, last_result)} · {elapsed:.2f}s")
            except Exception as error:
                log(stage, f"ERROR · {error}")
                yield rows(stage, completed, str(error)), doc_id, document_stats(doc_id) if doc_id else {}, "\n".join(logs), artifact_update()
                return
            yield rows(done=completed), doc_id, document_stats(doc_id), "\n".join(logs), artifact_update()

    def run_one(
        stage, file_path, source_path, doc_id, knowledge_id, kind, recreate,
        graph_provider, graph_model, graph_api_key,
    ):
        source = file_path or source_path
        started = time.perf_counter()
        try:
            if stage == "preprocess":
                result = pipeline.preprocess(source)
                doc_id = result["doc_id"]
            elif stage == "extract":
                markdown = source if source and Path(source).suffix.lower() == ".md" else str(
                    load_settings().path(load_settings().paths.markdown) / f"{doc_id}.md"
                )
                result = extract.run(markdown)
            elif stage == "link":
                result = link.run(doc_id)
            elif stage == "chunk":
                result = chunk.run(doc_id)
            elif stage == "graph":
                result = graph.run(
                    doc_id,
                    kind=kind,
                    provider=graph_provider or None,
                    model=graph_model or None,
                    api_key=graph_api_key or None,
                )
            elif stage == "embed":
                result = embed.run(doc_id)
            else:
                result = index.run(
                    doc_id,
                    kind=kind,
                    knowledge_id=knowledge_id,
                    recreate=recreate,
                )
            elapsed = time.perf_counter() - started
            done = set(STAGES[: STAGES.index(stage) + 1])
            message = f"{time.strftime('%H:%M:%S')}  {stage.upper():<10} OK · {compact(stage, result)} · {elapsed:.2f}s"
            return rows(done=done), doc_id, document_stats(doc_id), message, artifact_update()
        except Exception as error:
            message = f"{time.strftime('%H:%M:%S')}  {stage.upper():<10} ERROR · {error}"
            return rows(stage, set(), str(error)), doc_id, document_stats(doc_id) if doc_id else {}, message, artifact_update()

    def stage_handler(stage: str):
        return lambda file_path, source_path, doc_id, knowledge_id, kind, recreate, graph_provider, graph_model, graph_api_key: run_one(
            stage, file_path, source_path, doc_id, knowledge_id, kind, recreate,
            graph_provider, graph_model, graph_api_key,
        )

    def refresh_artifacts():
        items = list_artifacts()
        names = [item["name"] for item in items]
        table = [[item["name"], item["size"], item["type"]] for item in items]
        return gr.update(choices=names, value=names[0] if names else None), table

    def preview_artifact(name):
        return read_artifact(name) if name else "Chưa có artifact."

    def save_offline_settings(
        excel_sheets, excel_id, unit, heading_level, child_min, child_max,
        overlap, table_rows, dense_model, sparse_model, rerank_model,
        qdrant_url, qdrant_local_path, knowledge_id, docs_collection, sql_collection, graph_collection,
        graph_enabled, graph_source_kinds, graph_provider, graph_model,
        entity_types, relationship_types, community_algorithm, community_resolution,
        generate_reports, max_reports, max_chunks,
    ):
        id_column = int(excel_id) if str(excel_id).strip().isdigit() else str(excel_id).strip()
        patch = {
            "preprocess": {
                "excel_sheets": [item.strip() for item in excel_sheets.split(",") if item.strip()],
                "excel_id_column": id_column,
            },
            "chunk": {
                "unit": unit,
                "heading_level": int(heading_level),
                "child_min": int(child_min),
                "child_max": int(child_max),
                "child_overlap": int(overlap),
                "table_rows": int(table_rows),
            },
            "embedding": {
                "dense_model": dense_model,
                "sparse_model": sparse_model,
                "rerank_model": rerank_model,
            },
            "graph": {
                "enabled": bool(graph_enabled),
                "method": "llm",
                "source_kinds": list(graph_source_kinds or []),
                "provider": graph_provider or None,
                "model": graph_model or None,
                "entity_types": [item.strip() for item in entity_types.split(",") if item.strip()],
                "relationship_types": [item.strip() for item in relationship_types.split(",") if item.strip()],
                "community_algorithm": community_algorithm,
                "community_resolution": float(community_resolution),
                "generate_reports": bool(generate_reports),
                "max_reports": int(max_reports),
                "max_chunks": int(max_chunks),
            },
            "index": {
                "url": qdrant_url,
                "local_path": qdrant_local_path.strip() or None,
                "knowledge_id": knowledge_id,
                "collections": {
                    knowledge_id: {
                        "docs": docs_collection,
                        "sql": sql_collection,
                        "graph": graph_collection,
                    },
                },
            },
        }
        saved = update_settings(patch)
        return {
            "preprocess": saved.preprocess.model_dump(mode="json"),
            "chunk": saved.chunk.model_dump(mode="json"),
            "embedding": saved.embedding.model_dump(mode="json"),
            "graph": saved.graph.model_dump(mode="json"),
            "index": saved.index.model_dump(mode="json"),
        }

    def knowledge_collections(knowledge_id):
        current = load_settings().index
        mapping = current.collections[knowledge_id]
        return mapping["docs"], mapping["sql"], mapping["graph"]

    def graph_choices():
        base = load_settings().path(load_settings().paths.artifacts)
        return [path.name.removesuffix(".graph.json") for path in sorted(base.glob("*.graph.json"))]

    def show_graph(doc_id):
        if not doc_id:
            return "<p>Chưa có graph artifact.</p>", {}, []
        data = graph.load(doc_id)
        report_rows = [
            [report["community_id"], report["title"], len(report["node_ids"]), report["text"]]
            for report in data["reports"]
        ]
        return graph.html_view(doc_id), data.get("stats", {}), report_rows

    def refresh_graphs():
        choices = graph_choices()
        selected = choices[0] if choices else None
        view, stats, reports = show_graph(selected) if selected else ("<p>Chưa có graph artifact.</p>", {}, [])
        return gr.update(choices=choices, value=selected), view, stats, reports

    def run_graph_eval(doc_id, knowledge_id, split):
        result = graph_eval.evaluate(doc_id, knowledge_id=knowledge_id, split=split)
        rows = [
            [case["id"], case["table_recall"], case["complete"], case["connected"], case["same_community"], ", ".join(case["missing"])]
            for case in result["per_case"]
        ]
        summary = {
            "path": result["path"],
            "metrics": result["metrics"],
            "graph_stats": result["graph_stats"],
            "parameters": result["parameters"],
        }
        return summary, rows

    def save_settings(raw: str):
        return update_settings(json.loads(raw)).model_dump(mode="json")

    with gr.Blocks(title="Branch SQL MVP · Knowledge Studio") as ui:
        gr.Markdown("# Knowledge Studio · branch_sql_MVP\nOffline indexing rõ từng stage, không queue và không lưu run log.")

        with gr.Tab("Offline Studio"):
            with gr.Tab("Pipeline"):
                with gr.Row():
                    with gr.Column(scale=1, min_width=320):
                        gr.Markdown("### Knowledge source")
                        source_file = gr.File(type="filepath", label="Upload .md / .docx / .pdf / .xlsx")
                        source_path = gr.Textbox(label="Hoặc đường dẫn / tên file trong data/raw/sql")
                        knowledge_id = gr.Dropdown(
                            list(settings.index.collections),
                            value=settings.index.knowledge_id,
                            label="Knowledge ID",
                        )
                        knowledge_kind = gr.Radio(["docs", "sql"], value="docs", label="Knowledge kind")
                        recreate_index = gr.Checkbox(value=False, label="Recreate collection trước khi index")
                        with gr.Accordion("Graph run override", open=False):
                            graph_run_provider = gr.Dropdown(
                                list(settings.api.providers),
                                value=settings.graph.provider or settings.api.provider,
                                label="Graph provider",
                            )
                            graph_run_model = gr.Textbox(
                                value=settings.graph.model or settings.api.model,
                                label="Graph model",
                            )
                            graph_run_api_key = gr.Textbox(type="password", label="Graph API key (không lưu)")
                        current_doc_id = gr.Textbox(label="doc_id", placeholder="Tự điền sau preprocess")
                        run_all_button = gr.Button("Run offline pipeline", variant="primary")
                        gr.Markdown("#### Run one stage")
                        stage_buttons = {}
                        for number, stage in enumerate(STAGES, 1):
                            stage_buttons[stage] = gr.Button(f"{number:02d} · {stage}", size="sm")

                    with gr.Column(scale=2, min_width=560):
                        gr.Markdown("### Pipeline status")
                        stage_table = gr.Dataframe(
                            value=rows(),
                            headers=["Stage", "Status", "Result"],
                            datatype=["str", "str", "str"],
                            interactive=False,
                            row_count=(len(STAGES), "fixed"),
                            column_count=(3, "fixed"),
                            wrap=True,
                        )
                        with gr.Row():
                            run_stats = gr.JSON(label="Artifact statistics")
                            run_console = gr.Code(label="Processing console", language=None, lines=16)

                outputs = [stage_table, current_doc_id, run_stats, run_console]
                artifact_select_hidden = gr.Dropdown(visible=False)
                outputs.append(artifact_select_hidden)
                pipeline_inputs = [
                    source_file, source_path, knowledge_id, knowledge_kind, recreate_index,
                    graph_run_provider, graph_run_model, graph_run_api_key,
                ]
                run_all_button.click(run_all, pipeline_inputs, outputs)
                single_inputs = [
                    source_file, source_path, current_doc_id, knowledge_id, knowledge_kind, recreate_index,
                    graph_run_provider, graph_run_model, graph_run_api_key,
                ]
                for stage, button in stage_buttons.items():
                    button.click(stage_handler(stage), single_inputs, outputs)

            with gr.Tab("Offline settings"):
                gr.Markdown("### Cấu hình nhanh\nCác giá trị được validate rồi ghi vào `settings.json`; API key không nằm ở đây.")
                with gr.Row():
                    with gr.Column():
                        excel_sheets = gr.Textbox(value=",".join(settings.preprocess.excel_sheets), label="Excel sheets")
                        excel_id = gr.Textbox(value=str(settings.preprocess.excel_id_column), label="Excel ID column")
                        chunk_unit = gr.Radio(["token", "character"], value=settings.chunk.unit, label="Chunk unit")
                        heading_level = gr.Number(value=settings.chunk.heading_level, precision=0, label="Unit heading level")
                        child_min = gr.Number(value=settings.chunk.child_min, precision=0, label="Child minimum")
                        child_max = gr.Number(value=settings.chunk.child_max, precision=0, label="Child maximum")
                        overlap = gr.Number(value=settings.chunk.child_overlap, precision=0, label="Child overlap")
                        table_rows = gr.Number(value=settings.chunk.table_rows, precision=0, label="Rows per table chunk")
                    with gr.Column():
                        dense_model = gr.Textbox(value=settings.embedding.dense_model, label="Dense model")
                        sparse_model = gr.Textbox(value=settings.embedding.sparse_model, label="Sparse model")
                        rerank_model = gr.Textbox(value=settings.embedding.rerank_model, label="Reranker")
                        qdrant_url = gr.Textbox(value=settings.index.url, label="Qdrant URL")
                        qdrant_local_path = gr.Textbox(
                            value=settings.index.local_path or "",
                            label="Qdrant local path (để trống nếu dùng URL)",
                        )
                        settings_knowledge_id = gr.Dropdown(
                            list(settings.index.collections),
                            value=settings.index.knowledge_id,
                            label="Default knowledge ID",
                        )
                        selected_collections = settings.index.collections[settings.index.knowledge_id]
                        docs_collection = gr.Textbox(value=selected_collections["docs"], label="Docs collection")
                        sql_collection = gr.Textbox(value=selected_collections["sql"], label="SQL collection")
                        graph_collection = gr.Textbox(value=selected_collections["graph"], label="Graph collection")
                        settings_knowledge_id.change(
                            knowledge_collections,
                            settings_knowledge_id,
                            [docs_collection, sql_collection, graph_collection],
                        )
                    with gr.Column():
                        graph_enabled = gr.Checkbox(value=settings.graph.enabled, label="Enable GraphRAG")
                        graph_source_kinds = gr.CheckboxGroup(
                            ["docs", "sql"],
                            value=settings.graph.source_kinds,
                            label="Graph chunk sources",
                        )
                        gr.Markdown("Graph extraction: **SQLGraphAgent · LLM API · structured output**")
                        graph_provider = gr.Dropdown(
                            list(settings.api.providers),
                            value=settings.graph.provider or settings.api.provider,
                            label="Graph provider",
                        )
                        graph_model = gr.Textbox(value=settings.graph.model or settings.api.model, label="Graph model")
                        entity_types = gr.Textbox(value=",".join(settings.graph.entity_types), label="Entity types")
                        relationship_types = gr.Textbox(
                            value=",".join(settings.graph.relationship_types),
                            label="Relationship types",
                        )
                        community_algorithm = gr.Dropdown(
                            ["louvain", "greedy_modularity", "connected_components"],
                            value=settings.graph.community_algorithm,
                            label="Community algorithm",
                        )
                        community_resolution = gr.Number(
                            value=settings.graph.community_resolution,
                            label="Community resolution",
                        )
                        generate_reports = gr.Checkbox(value=settings.graph.generate_reports, label="Generate community reports")
                        max_reports = gr.Number(value=settings.graph.max_reports, precision=0, label="Max LLM reports (0 = none)")
                        max_chunks = gr.Number(value=settings.graph.max_chunks, precision=0, label="Max chunks (0 = all)")
                save_offline = gr.Button("Validate và lưu offline settings", variant="primary")
                offline_saved = gr.JSON(label="Settings đã lưu")
                save_offline.click(
                    save_offline_settings,
                    [excel_sheets, excel_id, chunk_unit, heading_level, child_min, child_max,
                     overlap, table_rows, dense_model, sparse_model, rerank_model,
                     qdrant_url, qdrant_local_path, settings_knowledge_id, docs_collection, sql_collection, graph_collection,
                     graph_enabled, graph_source_kinds, graph_provider, graph_model,
                     entity_types, relationship_types, community_algorithm, community_resolution,
                     generate_reports, max_reports, max_chunks],
                    offline_saved,
                )

            with gr.Tab("Artifacts"):
                with gr.Row():
                    artifact_select = gr.Dropdown(
                        choices=[item["name"] for item in list_artifacts()],
                        label="Artifact",
                        scale=4,
                    )
                    refresh_button = gr.Button("Refresh", scale=1)
                artifact_table = gr.Dataframe(
                    value=[[item["name"], item["size"], item["type"]] for item in list_artifacts()],
                    headers=["name", "size", "type"],
                    interactive=False,
                )
                artifact_preview = gr.Code(label="Artifact preview", language=None, lines=24)
                refresh_button.click(refresh_artifacts, outputs=[artifact_select, artifact_table])
                artifact_select.change(preview_artifact, artifact_select, artifact_preview)

        initial_graphs = graph_choices()
        initial_graph = initial_graphs[0] if initial_graphs else None
        initial_view, initial_stats, initial_reports = show_graph(initial_graph) if initial_graph else (
            "<p>Chưa có graph artifact. Chạy stage graph trong Offline Studio.</p>", {}, []
        )
        with gr.Tab("Graph"):
            with gr.Row():
                graph_select = gr.Dropdown(choices=initial_graphs, value=initial_graph, label="Graph document", scale=4)
                graph_refresh = gr.Button("Refresh graph", scale=1)
            graph_canvas = gr.HTML(value=initial_view, label="Graph diagram")
            with gr.Row():
                graph_stats = gr.JSON(value=initial_stats, label="Graph statistics")
                graph_reports = gr.Dataframe(
                    value=initial_reports,
                    headers=["community", "title", "nodes", "report"],
                    interactive=False,
                    wrap=True,
                )
            graph_select.change(show_graph, graph_select, [graph_canvas, graph_stats, graph_reports])
            graph_refresh.click(refresh_graphs, outputs=[graph_select, graph_canvas, graph_stats, graph_reports])

        with gr.Tab("Eval dev"):
            gr.Markdown(
                "Đo graph bằng `Relevant Chunks` trong Excel. Dùng **dev** để chỉnh tham số; "
                "chỉ dùng **test** khi báo cáo cuối."
            )
            with gr.Row():
                eval_doc = gr.Dropdown(choices=initial_graphs, value=initial_graph, label="Graph document")
                eval_knowledge = gr.Dropdown(
                    list(settings.index.collections), value=settings.index.knowledge_id, label="Knowledge ID"
                )
                eval_split = gr.Radio(["dev", "test"], value=settings.eval.split, label="Split")
                eval_button = gr.Button("Run graph eval", variant="primary")
            eval_summary = gr.JSON(label="Metrics + run parameters")
            eval_cases = gr.Dataframe(
                headers=["case", "table_recall", "complete", "connected", "same_community", "missing"],
                interactive=False,
                wrap=True,
            )
            eval_button.click(run_graph_eval, [eval_doc, eval_knowledge, eval_split], [eval_summary, eval_cases])

        with gr.Tab("Chat one-shot"):
            with gr.Row():
                chat_knowledge_id = gr.Dropdown(
                    list(settings.index.collections),
                    value=settings.index.knowledge_id,
                    label="Knowledge ID",
                )
                provider = gr.Dropdown(list(settings.api.providers), value=settings.api.provider, label="Provider")
                model = gr.Textbox(value=settings.api.model, label="Model")
                api_key = gr.Textbox(type="password", label="API key (không lưu)")
            with gr.Row():
                mode = gr.Dropdown(["semantic", "keyword", "hybrid"], value=settings.retrieval.mode, label="Retrieval")
                semantic_weight = gr.Slider(0, 1, value=settings.retrieval.semantic_weight, label="Semantic weight")
                keyword_weight = gr.Slider(0, 1, value=settings.retrieval.keyword_weight, label="Keyword weight")
            gr.ChatInterface(
                fn=chat_once,
                additional_inputs=[
                    chat_knowledge_id,
                    provider,
                    model,
                    api_key,
                    mode,
                    semantic_weight,
                    keyword_weight,
                ],
            )

        with gr.Tab("Raw settings"):
            raw_settings = gr.Code(
                value=json.dumps(settings.model_dump(mode="json"), ensure_ascii=False, indent=2),
                language="json",
                label="settings.json (không nhận secret)",
            )
            save_button = gr.Button("Validate và lưu")
            saved = gr.JSON(label="Settings đã lưu")
            save_button.click(save_settings, raw_settings, saved)
    return ui


def create_app() -> FastAPI:
    import gradio as gr

    theme = gr.themes.Soft(primary_hue="amber", neutral_hue="slate")
    return gr.mount_gradio_app(create_api(), create_ui(), path="/ui", theme=theme)


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)

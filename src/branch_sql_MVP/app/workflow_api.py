"""Typed durable workflow job endpoints."""
from functools import lru_cache
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from typing import Any
from ..settings import ROOT, load_settings
from ..workflow.runtime import RunManager
from ..workflow.store import load_workflow
from ..workflow.registry import node_registry

router = APIRouter()

@lru_cache(maxsize=1)
def manager():
    return RunManager(ROOT / '.runtime/studio/runs')

class RunRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    workflow_id: str
    revision: int = Field(ge=1)
    inputs: dict[str, Any] = Field(default_factory=dict)
    api_key: str | None = None
    dataset_revision: str | None = None
    dataset_id: str | None = None

class NodeTestRequest(BaseModel):
    run_id: str | None = None
    scope: list[str] = Field(default_factory=list)
    model_config = ConfigDict(extra='forbid')
    inputs: dict[str, Any] = Field(default_factory=dict)
    revision: int | None = Field(default=None, ge=1)
    api_key: str | None = None

@router.post('/studio/runs')
def submit(request: RunRequest):
    from .studio import WORKFLOW_ROOT
    try:
        definition = load_workflow(WORKFLOW_ROOT, request.workflow_id, request.revision)
        settings = load_settings()
        if definition.kind == "offline":
            from ..data.import_dataset import workspace
            start = next((n for n in definition.nodes if n.type == "start"), None)
            name = start.inputs.get("name").value if start and "name" in start.inputs else None
            if name and (workspace()/name/"dataset.json").exists():
                raise ValueError("Dataset already ready. Upload with a new version name to change its artifacts.")
        inputs = {"mode": "sql_only", "difficulty": "unknown", "evidence": "", **request.inputs}
        revision = request.dataset_revision
        if request.dataset_id:
            from ..data.import_dataset import datasets, dataset_settings, workspace
            from ..workflow.nodes.offline import digest
            record = next((row for row in datasets() if row["id"] == request.dataset_id), None)
            if record is None:
                raise FileNotFoundError(request.dataset_id)
            requires_index = definition.requires_index or definition.defaults.get("scenario", "P1") != "P1"
            if requires_index and not record["indexed"]:
                raise ValueError("Dataset requires a completed vector index")
            folder = workspace() / record["id"]
            revision = digest(folder / "database.sqlite") + digest(folder / "business.md")
            if record.get("revision") and revision != record["revision"]:
                raise ValueError("Dataset artifacts changed after registration; import a new version")
            if request.dataset_revision and request.dataset_revision != revision:
                raise ValueError("Dataset revision changed")
            inputs.update(database=str(folder / "database.sqlite"), business_path=str(folder / "business.md"),
                schema_catalog_path=str(folder / "schema.json"), event_index_path=str(folder / "events.json"),
                knowledge_id=record["knowledge_id"], doc_id=record["doc_id"])
            if not inputs.get("question"):
                inputs["question"] = record["question"]
            settings = dataset_settings(record, settings)
        return manager().submit(definition, inputs, settings, api_key=request.api_key,
                                dataset_revision=revision)
    except FileNotFoundError as error:
        raise HTTPException(404, 'Không tìm thấy workflow revision') from error
    except ValueError as error:
        raise HTTPException(422, str(error)) from error

@router.get('/studio/runs')
def runs():
    return manager().list()

@router.get('/studio/runs/{run_id}')
def run(run_id: str):
    try:
        return manager().get(run_id)
    except FileNotFoundError as error:
        raise HTTPException(404, 'Không tìm thấy run') from error

@router.get('/studio/runs/{run_id}/events')
def events(run_id: str, after: int = 0):
    try:
        return manager().events(run_id, after)
    except FileNotFoundError as error:
        raise HTTPException(404, 'Không tìm thấy run') from error

@router.post('/studio/runs/{run_id}/cancel')
def cancel(run_id: str):
    try:
        return manager().cancel(run_id)
    except FileNotFoundError as error:
        raise HTTPException(404, 'Không tìm thấy run') from error

@router.post('/studio/workflows/{workflow_id}/nodes/{node_id}/test')
def test_node(workflow_id: str, node_id: str, request: NodeTestRequest):
    from .studio import WORKFLOW_ROOT
    from ..workflow.compiler import compile_workflow
    from ..workflow.contracts import WorkflowDefinition, Reference
    from ..workflow.runtime import sanitize
    try:
        definition = load_workflow(WORKFLOW_ROOT, workflow_id, request.revision)
        for parent_id in request.scope:
            parent=next((n for n in definition.nodes if n.id==parent_id), None)
            if parent is None or 'body' not in parent.config:
                raise FileNotFoundError(parent_id)
            definition=WorkflowDefinition.model_validate(parent.config['body'])
        node = next((n.model_copy(deep=True) for n in definition.nodes if n.id == node_id), None)
        if node is None:
            raise FileNotFoundError(node_id)
        node.inputs = {key: Reference(value=value) for key, value in request.inputs.items()}
        isolated = WorkflowDefinition(id='node_test', kind=definition.kind, nodes=[node])
        settings=load_settings()
        node_outputs: dict = {}
        if request.run_id:
            record=manager().get(request.run_id)
            if record['workflow_id']!=workflow_id:
                raise ValueError('Run does not belong to this pipeline configuration')
            from ..settings import Settings
            settings=Settings.model_validate(record['settings'])
            # Nodes such as `merge` read sibling outputs off the run state, so
            # replay the recorded outputs of the same scope the node lives in.
            if not request.scope:
                node_outputs = dict((record.get('result') or {}).get('node_outputs') or {})
        result = compile_workflow(isolated, settings=settings, api_key=request.api_key).invoke({'inputs': request.inputs, 'node_outputs': node_outputs})
        return sanitize(result, request.api_key)
    except FileNotFoundError as error:
        raise HTTPException(404, 'Không tìm thấy workflow/node') from error
    except (ValueError, RuntimeError, KeyError) as error:
        raise HTTPException(422, sanitize(str(error), request.api_key)) from error


from fastapi import File, Form, UploadFile

@router.post("/studio/datasets/upload")
async def upload_dataset(name: str = Form(...), question: str = Form(""),
                         database: UploadFile = File(...), business: UploadFile = File(...),
                         index: bool = Form(False), graph: bool = Form(False)):
    from ..data.import_dataset import workspace
    from ..workflow.templates import offline_template
    import re, shutil
    from uuid import uuid4
    from pathlib import Path
    if not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", name):
        raise HTTPException(422, "Invalid dataset name")
    if (workspace()/name).exists():
        raise HTTPException(409, "Dataset name exists; resume its offline workflow or choose a new version")
    suffix = Path(business.filename or "").suffix.lower()
    if Path(database.filename or "").suffix.lower() not in {".db", ".sqlite"} or suffix not in {".md", ".docx", ".xlsx", ".pdf"}:
        raise HTTPException(422, "Unsupported source format")
    folder = ROOT / ".runtime/studio/uploads" / uuid4().hex
    folder.mkdir(parents=True)
    dbpath=folder/(name+".sqlite"); docpath=folder/(name+suffix)
    for upload,path in ((database,dbpath),(business,docpath)):
        with path.open("wb") as target:
            shutil.copyfileobj(upload.file,target)
    return offline_template(name,str(dbpath),str(docpath),question,index or graph,graph).model_dump(mode="json")

@router.get("/studio/datasets/status")
def dataset_status():
    from ..data.import_dataset import workspace
    import json
    return [json.loads(path.read_text(encoding="utf-8")) for path in workspace().glob("*/offline-status.json")]


@router.get('/studio/datasets')
def registered_datasets():
    from ..data.import_dataset import available_datasets
    return available_datasets()

@router.get('/studio/datasets/{dataset_id}')
def dataset_detail(dataset_id: str):
    from ..data.import_dataset import datasets, workspace
    from ..workflow.nodes.offline import digest
    record=next((row for row in datasets() if row['id']==dataset_id),None)
    if record is None:
        raise HTTPException(404,'Dataset is not ready')
    folder=workspace()/record['id']
    artifacts=[{'name':str(path.relative_to(folder)), 'bytes':path.stat().st_size,'sha256':digest(path)}
        for path in folder.rglob('*') if path.is_file() and 'cache' not in path.relative_to(folder).parts]
    return {**record,'status':'ready','artifacts':artifacts}


class PrepareRepositoryDataset(BaseModel):
    dataset_id: str
    indexed: bool = False
    question: str = ''

@router.post('/studio/datasets/prepare-repository')
def prepare_repository(request: PrepareRepositoryDataset):
    from ..data.import_dataset import available_datasets
    from ..data import service
    from ..workflow.templates import offline_template
    record=next((row for row in available_datasets() if row['id']==request.dataset_id and row.get('source')=='repository'),None)
    if record is None:
        raise HTTPException(404,'Không tìm thấy dữ liệu nguồn; tải lại danh sách')
    try:
        source=service.dataset(record['name'],split=record['split'])
        database=service.build_database(record['name'],split=record['split'],overwrite=False)
        return offline_template(record['import_name'],str(database['path']),str(source.business_document.resolve()),
            request.question,request.indexed).model_dump(mode='json')
    except (ValueError,FileNotFoundError) as error:
        raise HTTPException(422,str(error)) from error

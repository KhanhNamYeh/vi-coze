"""Knowledge Studio — REST + phục vụ UI. Chặng `api`.

    uv run --extra api python -m src.branch_sql.api      http://127.0.0.1:8000

Poll là chính, stream là phụ. `GET /api/runs/{id}` trả trạng thái và chặng hiện
tại, UI hỏi lại mỗi giây - reload trang giữa chừng vẫn thấy đúng tiến độ, và job
sống lâu hơn cái tab. Endpoint log chỉ phục vụ pane console; mất nó thì UI vẫn
chạy đúng. Đây là cách Dify làm (trả `batch ID` rồi poll), và nó đúng hơn stream
stdout vì hợp đồng là MÁY TRẠNG THÁI chứ không phải dòng log.

Knowledge hợp nhất từ hai nguồn: khai sẵn trong `config/sql.json` (chỉ đọc) và do
UI tạo trong SQLite (sửa được). Trường `origin` nói rõ cái nào là cái nào, để giao
diện không mời người dùng sửa thứ nó không sửa được.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from ..config import CFG, DOC_SUFFIXES, RAW_DIR, ROOT, listdir
from . import store
from .queue import RUNNER, log_path, processed_dir

STATIC = Path(__file__).parent / "static"

app = FastAPI(title="vi-coze · Knowledge Studio", docs_url="/api/docs")


@app.on_event("startup")
def _startup() -> None:
    store.init()
    # Đồng bộ dự án khai trong profile vào DB để UI thấy chúng ngay lần đầu chạy.
    for pid in CFG.projects:
        if not any(p["id"] == pid for p in store.projects()):
            store.upsert_project(pid, f"Dự án {pid}", CFG.description)
    RUNNER.start()


# ---- model ----------------------------------------------------------------

class ProjectIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = ""


class KnowledgeIn(BaseModel):
    """Form tạo knowledge. `chunk` nhận nguyên khối `ChunkCfg` của profile.

    Không validate `chunk` ở đây bằng ChunkCfg vì một cấu hình sai chỉ được phép
    làm hỏng job của chính knowledge này - `queue.write_profile` sinh profile tạm
    chỉ chứa nó, và lỗi lộ ra lúc chạy chứ không chặn cả UI.
    """

    id: str = Field(pattern=r"^[a-z0-9_]{2,40}$")
    source: str
    collection: str = Field(min_length=1)
    chunk: dict | None = None


class RunIn(BaseModel):
    project: int
    knowledge_id: str
    recreate: bool = False


# ---- project + knowledge --------------------------------------------------

def _knowledge_of(project: int) -> list[dict]:
    """Hợp nhất knowledge của profile và của SQLite, SQLite thắng khi trùng id."""
    out: dict[str, dict] = {}
    for k in CFG.knowledge_of(project):
        out[k.id] = {
            "id": k.id, "source": k.source, "project": project,
            "collection": k.collection_for(project),
            "chunk": json.loads(CFG.chunk_of(k).model_dump_json(exclude_none=True)),
            "origin": "profile",
        }
    for row in store.knowledge(project):
        out[row["kid"]] = {
            "id": row["kid"], "source": row["source"], "project": project,
            "collection": row["collection"], "chunk": row["chunk"], "origin": "studio",
        }
    return list(out.values())


@app.get("/api/projects")
def list_projects() -> list[dict]:
    rows = {p["id"]: p for p in store.projects()}
    return [
        {**rows.get(pid, {"id": pid, "name": f"Dự án {pid}", "description": ""}),
         "knowledge": _knowledge_of(pid)}
        for pid in sorted({*CFG.projects, *rows})
    ]


@app.post("/api/projects", status_code=201)
def create_project(body: ProjectIn) -> dict:
    pid = store.next_project_id()
    store.upsert_project(pid, body.name, body.description)
    return {"id": pid, "name": body.name, "description": body.description, "knowledge": []}


@app.get("/api/projects/{project}/knowledge")
def list_knowledge(project: int) -> list[dict]:
    return _knowledge_of(project)


@app.post("/api/projects/{project}/knowledge", status_code=201)
def create_knowledge(project: int, body: KnowledgeIn) -> dict:
    if not (RAW_DIR / body.source).exists():
        raise HTTPException(400, f"không thấy nguồn '{body.source}' trong {RAW_DIR.name}/")
    store.upsert_knowledge(project, body.id, body.source, body.collection, body.chunk)
    return {**body.model_dump(), "project": project, "origin": "studio"}


# ---- nguồn ----------------------------------------------------------------

SAFE_NAME = re.compile(r"^[^/\\]{1,120}$")


@app.get("/api/sources")
def list_sources() -> list[dict]:
    return [
        {"name": n, "size": (RAW_DIR / n).stat().st_size,
         "supported": Path(n).suffix.lower() in DOC_SUFFIXES}
        for n in listdir(RAW_DIR)
    ]


@app.post("/api/sources", status_code=201)
async def upload_source(file: UploadFile) -> dict:
    name = Path(file.filename or "").name
    if not SAFE_NAME.match(name):
        raise HTTPException(400, "tên file không hợp lệ")
    if Path(name).suffix.lower() not in DOC_SUFFIXES:
        raise HTTPException(
            400, f"đuôi '{Path(name).suffix}' không có trong parse.suffixes "
                 f"({', '.join(sorted(DOC_SUFFIXES))})")
    dst = RAW_DIR / name
    if dst.exists():
        raise HTTPException(409, f"'{name}' đã có - đổi tên hoặc xoá bản cũ trước")

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(await file.read())
    return {"name": name, "size": dst.stat().st_size}


# ---- run ------------------------------------------------------------------

@app.post("/api/runs", status_code=202)
def create_run(body: RunIn) -> dict:
    if not any(k["id"] == body.knowledge_id for k in _knowledge_of(body.project)):
        raise HTTPException(
            404, f"dự án {body.project} không có knowledge '{body.knowledge_id}'")
    rid = RUNNER.submit(body.project, body.knowledge_id, recreate=body.recreate)
    return {**store.get_run(rid), "queue_depth": RUNNER.depth()}


@app.get("/api/runs")
def list_runs(project: int | None = None, limit: int = 50) -> list[dict]:
    return store.runs(project, limit)


@app.get("/api/runs/{run_id}")
def get_run(run_id: str) -> dict:
    run = store.get_run(run_id)
    if run is None:
        raise HTTPException(404, f"không có run '{run_id}'")
    return {**run, "stage_order": list(store.STAGES), "queue_depth": RUNNER.depth()}


@app.get("/api/runs/{run_id}/log", response_class=PlainTextResponse)
def get_log(run_id: str, offset: int = 0) -> str:
    """Tail log từ `offset` byte. UI giữ offset để chỉ lấy phần mới."""
    run = store.get_run(run_id)
    if run is None:
        raise HTTPException(404, f"không có run '{run_id}'")
    path = log_path(run["project"], run_id)
    if not path.exists():
        return ""
    with path.open("r", encoding="utf-8", errors="replace") as fh:
        fh.seek(max(offset, 0))
        return fh.read()


# ---- verify ---------------------------------------------------------------

@app.get("/api/projects/{project}/artifacts")
def list_artifacts(project: int) -> list[dict]:
    """Artifact đang có trên đĩa - nguồn sự thật để đối chiếu với DB."""
    base = processed_dir(project)
    if not base.is_dir():
        return []
    return sorted(
        ({"name": p.name, "size": p.stat().st_size} for p in base.iterdir() if p.is_file()),
        key=lambda r: r["name"],
    )


# ---- static ---------------------------------------------------------------

@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


if STATIC.is_dir():
    app.mount("/static", StaticFiles(directory=STATIC), name="static")

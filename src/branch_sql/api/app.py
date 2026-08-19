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
from .queue import RUNNER, log_path, processed_dir, source_doc_id

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
            # `{project}` phải được thay ở MỌI nơi đọc collection, không chỉ ở
            # KnowledgeCfg - nếu không, knowledge tạo từ UI sẽ trỏ vào một tên
            # collection chứa dấu ngoặc và Qdrant trả 404 khó lần ra.
            "collection": row["collection"].format(project=project),
            "chunk": row["chunk"], "origin": "studio",
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
    files = [*(p for p in base.iterdir() if p.is_file()),
             *((base / "runs").iterdir() if (base / "runs").is_dir() else [])]
    return sorted(
        ({"name": p.name, "size": p.stat().st_size,
          "kind": p.suffix.lstrip(".") or "file"} for p in files if p.is_file()),
        key=lambda r: r["name"],
    )


def _tok_stats(values: list[int]) -> dict:
    v = sorted(values)
    return {"n": len(v), "min": v[0], "p50": v[len(v) // 2], "max": v[-1]} if v else {"n": 0}


@app.get("/api/runs/{run_id}/stats")
def run_stats(run_id: str) -> dict:
    """Số liệu THẬT của từng chặng, đọc từ artifact trên đĩa.

    Panel chi tiết của UI vẽ từ đây thay vì đoán: mỗi chặng chỉ báo cái nó thật
    sự ghi ra được. Chặng chưa chạy xong thì không có khoá tương ứng - giao diện
    hiện "đang chạy" chứ không bịa số.
    """
    run = store.get_run(run_id)
    if run is None:
        raise HTTPException(404, f"không có run '{run_id}'")
    doc_id = source_doc_id(run["project"], run["kid"])
    base = processed_dir(run["project"])
    out: dict = {"doc_id": doc_id, "dir": str(base.relative_to(ROOT)).replace("\\", "/")}
    if not doc_id:
        return out

    md = base / f"{doc_id}.md"
    if md.exists():
        text = md.read_text(encoding="utf-8")
        lines = text.splitlines()
        out["parse"] = {
            "chars": len(text), "lines": len(lines),
            "h1": sum(1 for l in lines if l.startswith("# ")),
            "h2": sum(1 for l in lines if l.startswith("## ")),
            "tables": sum(1 for l in lines if l.startswith("|")),
        }

    ex = base / f"{doc_id}.extract.json"
    if ex.exists():
        ir = json.loads(ex.read_text(encoding="utf-8"))
        els = ir["elements"]
        mods: dict[str, int] = {}
        roles: dict[str, int] = {}
        for e in els:
            mods[e["modality"]] = mods.get(e["modality"], 0) + 1
            if e.get("role"):
                roles[e["role"]] = roles.get(e["role"], 0) + 1
        out["extract"] = {"elements": len(els), "modality": mods, "roles": roles,
                          "rows": sum(e.get("n_rows", 0) for e in els),
                          "warnings": ir.get("warnings", [])}

    li = base / f"{doc_id}.linked.json"
    if li.exists():
        els = json.loads(li.read_text(encoding="utf-8"))["elements"]
        out["link"] = {
            "elements": len(els),
            "roots": sum(1 for e in els if not e.get("parent_id")),
            "with_parent": sum(1 for e in els if e.get("parent_id")),
            "ancestors": sum(1 for e in els if e.get("table") or e.get("section")),
        }

    ch = base / f"{doc_id}.chunks.jsonl"
    if ch.exists():
        rows = [json.loads(l) for l in ch.read_text(encoding="utf-8").splitlines() if l.strip()]
        out["chunk"] = {
            **_tok_stats([r["metadata"]["n_tokens"] or 0 for r in rows]),
            "split_units": sum(1 for r in rows if r["metadata"]["part"] != "1/1"),
            "with_neighbor": sum(1 for r in rows
                                 if r["metadata"].get("prev_chunk_id")
                                 or r["metadata"].get("next_chunk_id")),
            "parents": sum(1 for _ in (base / f"{doc_id}.parents.jsonl").read_text(
                encoding="utf-8").splitlines()) if (base / f"{doc_id}.parents.jsonl").exists() else 0,
            "sample": [{"table_name": r["metadata"]["table_name"],
                        "n_tokens": r["metadata"]["n_tokens"],
                        "head": r["page_content"][:160]} for r in rows[:6]],
        }

    npz = base / f"{doc_id}.vectors.npz"
    if npz.exists():
        import numpy as np

        data = np.load(npz, allow_pickle=True)
        vec = data["vectors"]
        out["embed"] = {"vectors": int(vec.shape[0]), "dim": int(vec.shape[1]),
                        "dtype": str(vec.dtype), "model": str(data["model"]),
                        "finite": bool(np.isfinite(vec).all())}

    if run["status"] == "completed":
        coll = next((k["collection"] for k in _knowledge_of(run["project"])
                     if k["id"] == run["kid"]), None)
        if coll:
            try:
                from ..offline.index.qdrant_store import get_client

                info = get_client().get_collection(coll)
                out["index"] = {
                    "collection": coll,
                    "points": get_client().count(coll, exact=True).count,
                    "vectors": list(info.config.params.vectors or {}),
                    "sparse": list(info.config.params.sparse_vectors or {}),
                }
            except Exception as e:  # noqa: BLE001
                out["index"] = {"collection": coll, "error": str(e)}
    return out


@app.get("/api/projects/{project}/artifacts/{name}", response_class=PlainTextResponse)
def read_artifact(project: int, name: str, limit: int = 400_000) -> str:
    """Đọc một artifact để xem trong tab Logs. Chặn đường dẫn thoát thư mục."""
    if not SAFE_NAME.match(name) or name.startswith("."):
        raise HTTPException(400, "tên file không hợp lệ")
    path = processed_dir(project) / name
    if not path.is_file():
        alt = processed_dir(project) / "runs" / name
        if not alt.is_file():
            raise HTTPException(404, f"không thấy '{name}'")
        path = alt
    return path.read_text(encoding="utf-8", errors="replace")[:limit]


# ---- static ---------------------------------------------------------------

@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


if STATIC.is_dir():
    app.mount("/static", StaticFiles(directory=STATIC), name="static")

"""Trạng thái vận hành của Knowledge Studio. Chặng `api`.

SQLite giữ project, knowledge và từng lần chạy. File `config/sql.json` KHÔNG được
UI ghi vào, và đây là lý do:

Profile được validate như một khối. Người dùng tạo một knowledge với collection
thiếu `{project}` là `KBConfig.load()` ném lỗi, và **cả hai dự án cùng chết** - cả
CLI lẫn UI. Cách ly hai hộp đen mà chặng `index` dựng ra sẽ mất sạch vì một ô nhập
sai trên trình duyệt.

Vì vậy ranh giới là:

    config/sql.json   mặc định của hệ: model embed, parse.suffixes, extract.roles,
                      khối `chunk` mặc định. Người sửa bằng editor.
    data/api.db       project, knowledge, BẢN CHỤP chunk config của từng knowledge,
                      trạng thái từng lần chạy. API ghi.

Lúc chạy job, `queue.py` sinh một profile TẠM từ mặc định cộng bản chụp của
knowledge rồi trỏ `VI_COZE_PROFILE` vào đó. Knowledge hỏng chỉ làm hỏng job của
chính nó.

Dùng SQL thuần chứ không ORM: ba bảng, vài câu lệnh. Một ORM ở đây là thêm một
tầng phải học mà không giấu đi được gì.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from ..config import ROOT

DB_PATH = ROOT / "data" / "api.db"

# Máy trạng thái của một lần chạy. Theo đúng mô hình Dify: một chuỗi tuyến tính
# cộng một nhánh lỗi, và `error` giữ được chặng hỏng lẫn traceback.
STAGES = ("parse", "extract", "link", "chunk", "embed", "index")
STATUS = ("queued", "running", "completed", "error", "cancelled")

SCHEMA = """
CREATE TABLE IF NOT EXISTS project (
    id          INTEGER PRIMARY KEY,
    name        TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS knowledge (
    kid         TEXT NOT NULL,
    project     INTEGER NOT NULL,
    source      TEXT NOT NULL,
    collection  TEXT NOT NULL,
    -- Bản chụp khối `chunk` tại thời điểm tạo. Sửa mặc định của profile về sau
    -- KHÔNG làm đổi cách một knowledge đã index được cắt.
    chunk_json  TEXT,
    created_at  TEXT NOT NULL,
    PRIMARY KEY (project, kid)
);

CREATE TABLE IF NOT EXISTS run (
    id          TEXT PRIMARY KEY,
    project     INTEGER NOT NULL,
    kid         TEXT NOT NULL,
    status      TEXT NOT NULL,
    stage       TEXT,
    error       TEXT,
    log_path    TEXT,
    stages_json TEXT NOT NULL DEFAULT '{}',
    queued_at   TEXT NOT NULL,
    started_at  TEXT,
    finished_at TEXT
);

CREATE INDEX IF NOT EXISTS run_by_project ON run(project, queued_at DESC);
"""

_lock = threading.Lock()


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@contextmanager
def connect(path: Path | None = None):
    """Kết nối có transaction. WAL để đọc không bị chặn bởi worker đang ghi."""
    path = path or DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def init(path: Path | None = None) -> None:
    with connect(path) as conn:
        conn.executescript(SCHEMA)


# ---- project ---------------------------------------------------------------

def upsert_project(pid: int, name: str, description: str = "", *,
                   path: Path | None = None) -> None:
    with connect(path) as conn:
        conn.execute(
            "INSERT INTO project (id, name, description, created_at) VALUES (?,?,?,?) "
            "ON CONFLICT(id) DO UPDATE SET name=excluded.name, "
            "description=excluded.description",
            (pid, name, description, now()),
        )


def projects(*, path: Path | None = None) -> list[dict]:
    with connect(path) as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM project ORDER BY id")]


def next_project_id(*, path: Path | None = None) -> int:
    with connect(path) as conn:
        row = conn.execute("SELECT COALESCE(MAX(id), 0) + 1 AS n FROM project").fetchone()
        return int(row["n"])


# ---- knowledge -------------------------------------------------------------

def upsert_knowledge(project: int, kid: str, source: str, collection: str,
                     chunk: dict | None = None, *, path: Path | None = None) -> None:
    with connect(path) as conn:
        conn.execute(
            "INSERT INTO knowledge (kid, project, source, collection, chunk_json, "
            "created_at) VALUES (?,?,?,?,?,?) "
            "ON CONFLICT(project, kid) DO UPDATE SET source=excluded.source, "
            "collection=excluded.collection, chunk_json=excluded.chunk_json",
            (kid, project, source, collection,
             json.dumps(chunk, ensure_ascii=False) if chunk else None, now()),
        )


def knowledge(project: int | None = None, *, path: Path | None = None) -> list[dict]:
    sql = "SELECT * FROM knowledge"
    args: tuple = ()
    if project is not None:
        sql += " WHERE project = ?"
        args = (project,)
    with connect(path) as conn:
        out = []
        for r in conn.execute(sql + " ORDER BY project, kid", args):
            row = dict(r)
            row["chunk"] = json.loads(row.pop("chunk_json")) if row["chunk_json"] else None
            out.append(row)
        return out


def get_knowledge(project: int, kid: str, *, path: Path | None = None) -> dict | None:
    return next((k for k in knowledge(project, path=path) if k["kid"] == kid), None)


# ---- run -------------------------------------------------------------------

def new_run(run_id: str, project: int, kid: str, *, path: Path | None = None) -> dict:
    with connect(path) as conn:
        conn.execute(
            "INSERT INTO run (id, project, kid, status, queued_at) VALUES (?,?,?,?,?)",
            (run_id, project, kid, "queued", now()),
        )
    return get_run(run_id, path=path)


def start_run(run_id: str, log_path: str, *, path: Path | None = None) -> None:
    with connect(path) as conn:
        conn.execute(
            "UPDATE run SET status='running', started_at=?, log_path=? WHERE id=?",
            (now(), log_path, run_id),
        )


def set_stage(run_id: str, stage: str, *, path: Path | None = None) -> None:
    """Ghi chặng đang chạy và mốc thời gian của nó.

    `stages_json` tích luỹ `{chặng: thời điểm xong}` nên dựng lại được biểu đồ
    thời gian sau khi job đã kết thúc, không cần giữ log trong bộ nhớ.
    """
    with connect(path) as conn:
        row = conn.execute("SELECT stages_json FROM run WHERE id=?", (run_id,)).fetchone()
        stages = json.loads(row["stages_json"]) if row else {}
        stages[stage] = now()
        conn.execute("UPDATE run SET stage=?, stages_json=? WHERE id=?",
                     (stage, json.dumps(stages), run_id))


def finish_run(run_id: str, status: str, error: str | None = None, *,
               path: Path | None = None) -> None:
    if status not in STATUS:
        raise ValueError(f"status '{status}' không hợp lệ - {STATUS}")
    with connect(path) as conn:
        conn.execute("UPDATE run SET status=?, error=?, finished_at=? WHERE id=?",
                     (status, error, now(), run_id))


def get_run(run_id: str, *, path: Path | None = None) -> dict | None:
    with connect(path) as conn:
        row = conn.execute("SELECT * FROM run WHERE id=?", (run_id,)).fetchone()
    if row is None:
        return None
    out = dict(row)
    out["stages"] = json.loads(out.pop("stages_json") or "{}")
    return out


def runs(project: int | None = None, limit: int = 50, *,
         path: Path | None = None) -> list[dict]:
    sql = "SELECT * FROM run"
    args: list = []
    if project is not None:
        sql += " WHERE project = ?"
        args.append(project)
    sql += " ORDER BY queued_at DESC LIMIT ?"
    args.append(limit)
    with connect(path) as conn:
        out = []
        for r in conn.execute(sql, args):
            row = dict(r)
            row["stages"] = json.loads(row.pop("stages_json") or "{}")
            out.append(row)
        return out


def reap_orphans(*, path: Path | None = None) -> int:
    """Job còn `running`/`queued` lúc khởi động là job của tiến trình đã chết.

    Hàng đợi nằm trong bộ nhớ nên server tắt là job mất; để nguyên trạng thái
    `running` thì UI hiện một thanh tiến độ đứng im vĩnh viễn. Đánh `error` với
    lý do rõ ràng để người dùng biết phải chạy lại.
    """
    with connect(path) as conn:
        cur = conn.execute(
            "UPDATE run SET status='error', error=?, finished_at=? "
            "WHERE status IN ('queued','running')",
            ("server dừng giữa chừng - chạy lại job này", now()),
        )
        return cur.rowcount

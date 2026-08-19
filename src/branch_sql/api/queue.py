"""Hàng đợi job, chạy pipeline offline qua subprocess. Chặng `api`.

MỘT luồng, chạy tuần tự. Không có Redis, không có Celery: hai service để chạy
lần lượt một job là chi phí vận hành không đổi lấy gì. Đổi lại, bấm nút ba lần
không sinh ra ba tiến trình cùng nạp model 1024 chiều.

Vì sao subprocess chứ không import thẳng:

    `src/branch_sql/config.py` chạy `CFG = KBConfig.load(PROFILE)` NGAY khi import
    rồi trải ra thành hằng số module (PROCESSED_DIR, COLLECTION, ...). Cả PROFILE
    lẫn VI_COZE_PROJECT đều phải có mặt TRƯỚC lúc import. Một server sống lâu
    không đổi dự án được trong cùng tiến trình.

Kèm theo hai cái lợi: docling và torch nặng, crash thì chết một job chứ không
chết server; và CLI vẫn là nguồn sự thật duy nhất về "một lần chạy làm gì" - API
không có đường đi riêng để lệch khỏi nó.

TIẾN ĐỘ SUY TỪ ARTIFACT, không parse stdout. `project.py` chạy cả sáu chặng im
lặng rồi mới in kết quả, nên stdout không nói được đang ở chặng nào. Nhưng mỗi
chặng ghi một file riêng, và sự xuất hiện của file đó CHÍNH LÀ tín hiệu chặng
xong. Không phải sửa một dòng nào trong `offline/`.
"""

from __future__ import annotations

import json
import os
import queue as _queue
import subprocess
import sys
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from ..config import CFG, ROOT, rel
from . import store

# Chặng -> đuôi artifact mà nó ghi ra. `index` không ghi file nên nhận biết bằng
# tiến trình kết thúc với mã 0.
STAGE_ARTIFACT = {
    "parse": ".md",
    "extract": ".extract.json",
    "link": ".linked.json",
    "chunk": ".chunks.jsonl",
    "embed": ".vectors.npz",
}
POLL_SECONDS = 0.4


@dataclass
class Job:
    run_id: str
    project: int
    kid: str
    recreate: bool = False


def run_id_for(kid: str, when: datetime | None = None) -> str:
    when = when or datetime.now()
    return f"{kid}_{when:%Y%m%d_%H%M%S}"


def processed_dir(project: int) -> Path:
    return ROOT / "data" / "processed" / CFG.kb / f"p{project}"


def log_path(project: int, run_id: str) -> Path:
    return processed_dir(project) / "runs" / f"{run_id}.log"


def write_profile(project: int, kid: str, dst: Path) -> Path:
    """Sinh profile TẠM: mặc định của hệ + bản chụp của một knowledge.

    Chỉ giữ đúng knowledge được chạy, nên một mục hỏng trong SQLite không kéo
    theo mục khác, và job này không thể vô tình chạm vào dữ liệu dự án kia.
    """
    profile = json.loads(CFG.model_dump_json(exclude_none=True))
    row = store.get_knowledge(project, kid)

    if row is None:
        # Knowledge khai sẵn trong config/sql.json, chưa qua UI.
        entry = next(
            (json.loads(k.model_dump_json(exclude_none=True))
             for k in CFG.knowledge_of(project) if k.id == kid),
            None,
        )
        if entry is None:
            raise ValueError(f"không có knowledge '{kid}' trong dự án {project}")
    else:
        entry = {
            "id": row["kid"], "source": row["source"], "project": project,
            "collection": row["collection"],
            **({"chunk": row["chunk"]} if row["chunk"] else {}),
        }

    profile["knowledge"] = [entry]
    profile.pop("project", None)  # đặt bằng VI_COZE_PROJECT lúc chạy
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8")
    return dst


def source_doc_id(project: int, kid: str) -> str | None:
    """`doc_id` mà chặng parse sẽ sinh ra, để biết đường theo dõi artifact nào."""
    from ..offline.parse.doc_parse import doc_id_of

    row = store.get_knowledge(project, kid)
    source = row["source"] if row else next(
        (k.source for k in CFG.knowledge_of(project) if k.id == kid), None)
    return doc_id_of(Path(source)) if source else None


class StageWatcher:
    """Theo dõi artifact xuất hiện -> báo chặng nào vừa xong.

    Xoá artifact cũ trước khi chạy là cách duy nhất để phân biệt "chặng vừa ghi
    xong" với "file của lần chạy trước còn sót". Không xoá thì mọi chặng đều báo
    xong ngay ở giây đầu tiên.
    """

    def __init__(self, project: int, doc_id: str | None):
        self.dir = processed_dir(project)
        self.doc_id = doc_id
        self.seen: set[str] = set()

    def clear(self) -> None:
        if not self.doc_id:
            return
        for suffix in STAGE_ARTIFACT.values():
            (self.dir / f"{self.doc_id}{suffix}").unlink(missing_ok=True)

    def poll(self) -> list[str]:
        """Các chặng vừa xong kể từ lần gọi trước, theo đúng thứ tự pipeline."""
        if not self.doc_id:
            return []
        done = []
        for stage, suffix in STAGE_ARTIFACT.items():
            if stage in self.seen:
                continue
            if (self.dir / f"{self.doc_id}{suffix}").exists():
                self.seen.add(stage)
                done.append(stage)
        return done


class Runner:
    """Hàng đợi + luồng chạy. Một instance cho cả tiến trình."""

    def __init__(self) -> None:
        self.q: _queue.Queue[Job] = _queue.Queue()
        self.current: str | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        store.reap_orphans()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="runner")
        self._thread.start()

    def submit(self, project: int, kid: str, *, recreate: bool = False) -> str:
        rid = run_id_for(kid)
        store.new_run(rid, project, kid)
        self.q.put(Job(rid, project, kid, recreate))
        return rid

    def depth(self) -> int:
        return self.q.qsize() + (1 if self.current else 0)

    def _loop(self) -> None:
        while True:
            job = self.q.get()
            self.current = job.run_id
            try:
                self._execute(job)
            except Exception as e:  # noqa: BLE001
                store.finish_run(job.run_id, "error", f"{type(e).__name__}: {e}")
            finally:
                self.current = None
                self.q.task_done()

    def _execute(self, job: Job) -> None:
        log = log_path(job.project, job.run_id)
        log.parent.mkdir(parents=True, exist_ok=True)
        store.start_run(job.run_id, rel(log))

        profile_name = f"_run_{job.run_id}"
        profile = write_profile(job.project, job.kid, ROOT / "config" / f"{profile_name}.json")

        watcher = StageWatcher(job.project, source_doc_id(job.project, job.kid))
        watcher.clear()

        cmd = [sys.executable, "-m", "src.branch_sql.offline", str(job.project)]
        if job.recreate:
            cmd.append("--recreate")
        env = {
            **os.environ,
            "VI_COZE_PROFILE": profile_name,
            "VI_COZE_PROJECT": str(job.project),
            "PYTHONIOENCODING": "utf-8",
            "PYTHONUNBUFFERED": "1",
        }

        tail: list[str] = []
        try:
            with log.open("w", encoding="utf-8") as fh:
                proc = subprocess.Popen(
                    cmd, cwd=ROOT, env=env, stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                    errors="replace", bufsize=1,
                )
                # Đọc stdout ở luồng riêng: nếu đọc trong vòng lặp poll thì
                # `readline` chặn và tiến độ chặng đứng im cho tới dòng kế tiếp.
                reader = threading.Thread(
                    target=self._drain, args=(proc, fh, tail), daemon=True)
                reader.start()

                while proc.poll() is None:
                    for stage in watcher.poll():
                        store.set_stage(job.run_id, stage)
                    reader.join(timeout=POLL_SECONDS)
                reader.join(timeout=5)

            for stage in watcher.poll():
                store.set_stage(job.run_id, stage)

            if proc.returncode == 0:
                store.set_stage(job.run_id, "index")
                store.finish_run(job.run_id, "completed")
            else:
                store.finish_run(
                    job.run_id, "error",
                    f"tiến trình thoát với mã {proc.returncode}\n" + "".join(tail[-30:]),
                )
        finally:
            profile.unlink(missing_ok=True)

    @staticmethod
    def _drain(proc, fh, tail: list[str]) -> None:
        for line in proc.stdout:
            fh.write(line)
            fh.flush()
            tail.append(line)
            if len(tail) > 200:
                del tail[:100]


RUNNER = Runner()

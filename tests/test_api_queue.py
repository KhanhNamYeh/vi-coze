"""Kiểm chứng api/queue — hàng đợi tuần tự và suy tiến độ từ artifact.

Không chạy pipeline thật: subprocess được thay bằng một script Python nhỏ tạo ra
đúng các file mà từng chặng ghi. Nhờ vậy test chạy dưới một giây và không cần
Qdrant, model embedding hay tài liệu nguồn.
"""

from __future__ import annotations

import sys
import textwrap
import time

import pytest

from src.branch_sql.api import queue as Q
from src.branch_sql.api import store


@pytest.fixture()
def db(tmp_path, monkeypatch):
    path = tmp_path / "api.db"
    store.init(path)
    monkeypatch.setattr(store, "DB_PATH", path)
    return path


class TestStageWatcher:
    def test_bao_chang_xong_theo_thu_tu_pipeline(self, tmp_path, monkeypatch):
        monkeypatch.setattr(Q, "processed_dir", lambda p: tmp_path)
        w = Q.StageWatcher(1, "doc")

        assert w.poll() == []
        (tmp_path / "doc.md").write_text("x", encoding="utf-8")
        assert w.poll() == ["parse"]
        assert w.poll() == []                       # không báo lại cái đã báo

        (tmp_path / "doc.extract.json").write_text("{}", encoding="utf-8")
        (tmp_path / "doc.linked.json").write_text("{}", encoding="utf-8")
        assert w.poll() == ["extract", "link"]      # đúng thứ tự pipeline

    def test_xoa_artifact_cu_truoc_khi_chay(self, tmp_path, monkeypatch):
        """Không xoá thì file của lần chạy trước làm mọi chặng báo xong ngay
        ở giây đầu tiên."""
        monkeypatch.setattr(Q, "processed_dir", lambda p: tmp_path)
        for suffix in Q.STAGE_ARTIFACT.values():
            (tmp_path / f"doc{suffix}").write_text("cũ", encoding="utf-8")

        w = Q.StageWatcher(1, "doc")
        w.clear()
        assert w.poll() == []
        assert not (tmp_path / "doc.md").exists()

    def test_khong_biet_doc_id_thi_khong_bao_gi(self, tmp_path, monkeypatch):
        monkeypatch.setattr(Q, "processed_dir", lambda p: tmp_path)
        w = Q.StageWatcher(1, None)
        w.clear()
        assert w.poll() == []


def fake_pipeline(tmp_path, *, doc_id="doc", fail_at=None, sleep=0.05) -> list[str]:
    """Script thay cho `python -m src.branch_sql.offline`: ghi artifact từng chặng."""
    script = tmp_path / "fake_stage.py"
    script.write_text(textwrap.dedent(f"""
        import sys, time, pathlib
        out = pathlib.Path({str(tmp_path)!r})
        stages = {list(Q.STAGE_ARTIFACT.items())!r}
        for stage, suffix in stages:
            if stage == {fail_at!r}:
                print("LỖI ở " + stage, flush=True)
                sys.exit(3)
            (out / ("{doc_id}" + suffix)).write_text("x", encoding="utf-8")
            print("xong " + stage, flush=True)
            time.sleep({sleep})
        print("index -> collection | 18 point", flush=True)
    """), encoding="utf-8")
    return [sys.executable, str(script)]


@pytest.fixture()
def runner(tmp_path, monkeypatch, db):
    """Runner chạy script giả thay vì pipeline thật."""
    monkeypatch.setattr(Q, "processed_dir", lambda p: tmp_path)
    monkeypatch.setattr(Q, "log_path", lambda p, rid: tmp_path / f"{rid}.log")
    monkeypatch.setattr(Q, "write_profile", lambda p, k, dst: dst)
    monkeypatch.setattr(Q, "source_doc_id", lambda p, k: "doc")
    r = Q.Runner()
    r.start()
    return r


def wait_for(run_id, statuses, timeout=20):
    end = time.time() + timeout
    while time.time() < end:
        run = store.get_run(run_id)
        if run and run["status"] in statuses:
            return run
        time.sleep(0.05)
    raise AssertionError(f"{run_id} không đạt {statuses}: {store.get_run(run_id)}")


class TestRunner:
    def test_chay_het_sau_chang(self, runner, tmp_path, monkeypatch):
        monkeypatch.setattr(Q.subprocess, "Popen", _popen_with(fake_pipeline(tmp_path)))
        rid = runner.submit(1, "k")
        run = wait_for(rid, {"completed", "error"})

        assert run["status"] == "completed", run["error"]
        assert run["stage"] == "index"
        assert list(run["stages"]) == list(store.STAGES)

    def test_that_bai_giu_ma_thoat_va_log(self, runner, tmp_path, monkeypatch):
        monkeypatch.setattr(Q.subprocess, "Popen",
                            _popen_with(fake_pipeline(tmp_path, fail_at="chunk")))
        rid = runner.submit(1, "k")
        run = wait_for(rid, {"completed", "error"})

        assert run["status"] == "error"
        assert "mã 3" in run["error"]
        assert run["stage"] == "link"          # dừng ngay trước chặng hỏng

    def test_ba_job_chay_tuan_tu_khong_song_song(self, runner, tmp_path, monkeypatch):
        """Bấm nút ba lần không được sinh ba tiến trình cùng nạp model."""
        monkeypatch.setattr(Q.subprocess, "Popen",
                            _popen_with(fake_pipeline(tmp_path, sleep=0.12)))
        ids = [runner.submit(1, f"k{i}") for i in range(3)]
        for rid in ids:
            wait_for(rid, {"completed", "error"})

        spans = []
        for rid in ids:
            run = store.get_run(rid)
            assert run["status"] == "completed", run["error"]
            spans.append((run["started_at"], run["finished_at"]))
        # job sau bắt đầu không sớm hơn lúc job trước kết thúc
        for (_, prev_end), (next_start, _) in zip(spans, spans[1:]):
            assert next_start >= prev_end

    def test_ghi_log_ra_file(self, runner, tmp_path, monkeypatch):
        monkeypatch.setattr(Q.subprocess, "Popen", _popen_with(fake_pipeline(tmp_path)))
        rid = runner.submit(1, "k")
        wait_for(rid, {"completed", "error"})
        assert "xong parse" in (tmp_path / f"{rid}.log").read_text(encoding="utf-8")


def _popen_with(cmd):
    """Thay lệnh thật bằng script giả, giữ nguyên mọi tham số còn lại."""
    real = Q.subprocess.Popen

    def factory(_cmd, **kw):
        return real(cmd, **kw)

    return factory

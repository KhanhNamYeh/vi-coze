"""Kiểm chứng api/store — SQLite giữ trạng thái vận hành.

Mọi test dùng DB tạm, không đụng `data/api.db` thật.
"""

from __future__ import annotations

import pytest

from src.branch_sql.api import store


@pytest.fixture()
def db(tmp_path):
    path = tmp_path / "api.db"
    store.init(path)
    return path


class TestProject:
    def test_them_va_doc_lai(self, db):
        store.upsert_project(1, "Bot BĐS", "docx", path=db)
        store.upsert_project(2, "Bot PDF", path=db)
        rows = store.projects(path=db)
        assert [r["id"] for r in rows] == [1, 2]
        assert rows[0]["name"] == "Bot BĐS"

    def test_upsert_khong_nhan_doi(self, db):
        store.upsert_project(1, "Tên cũ", path=db)
        store.upsert_project(1, "Tên mới", path=db)
        rows = store.projects(path=db)
        assert len(rows) == 1 and rows[0]["name"] == "Tên mới"

    def test_id_ke_tiep(self, db):
        assert store.next_project_id(path=db) == 1
        store.upsert_project(7, "x", path=db)
        assert store.next_project_id(path=db) == 8


class TestKnowledge:
    def test_giu_ban_chup_chunk(self, db):
        chunk = {"mode": "parent_child", "child_roles": ["sample_query"]}
        store.upsert_knowledge(1, "sql_sample", "a.xlsx", "sqlp1__sql", chunk, path=db)
        row = store.get_knowledge(1, "sql_sample", path=db)
        assert row["chunk"]["mode"] == "parent_child"
        assert row["chunk"]["child_roles"] == ["sample_query"]

    def test_khong_co_chunk_thi_none(self, db):
        store.upsert_knowledge(1, "k", "a.docx", "c", path=db)
        assert store.get_knowledge(1, "k", path=db)["chunk"] is None

    def test_cung_kid_o_hai_du_an_la_hai_ban_ghi(self, db):
        """`sql_sample` khai project [1,2] nên tồn tại độc lập ở cả hai."""
        store.upsert_knowledge(1, "sql_sample", "a.xlsx", "sqlp1__sql", path=db)
        store.upsert_knowledge(2, "sql_sample", "a.xlsx", "sqlp2__sql", path=db)
        assert len(store.knowledge(path=db)) == 2
        assert store.get_knowledge(1, "sql_sample", path=db)["collection"] == "sqlp1__sql"
        assert store.get_knowledge(2, "sql_sample", path=db)["collection"] == "sqlp2__sql"

    def test_loc_theo_du_an(self, db):
        store.upsert_knowledge(1, "a", "a.docx", "c1", path=db)
        store.upsert_knowledge(2, "b", "b.pdf", "c2", path=db)
        assert [k["kid"] for k in store.knowledge(1, path=db)] == ["a"]


class TestRun:
    def test_vong_doi_thanh_cong(self, db):
        store.new_run("r1", 1, "k", path=db)
        assert store.get_run("r1", path=db)["status"] == "queued"

        store.start_run("r1", "runs/r1.log", path=db)
        assert store.get_run("r1", path=db)["status"] == "running"

        for stage in store.STAGES:
            store.set_stage("r1", stage, path=db)
        store.finish_run("r1", "completed", path=db)

        run = store.get_run("r1", path=db)
        assert run["status"] == "completed"
        assert run["stage"] == "index"
        assert list(run["stages"]) == list(store.STAGES)   # mốc thời gian đủ sáu chặng
        assert run["finished_at"] and run["error"] is None

    def test_loi_giu_chang_hong_va_traceback(self, db):
        store.new_run("r1", 1, "k", path=db)
        store.start_run("r1", "x.log", path=db)
        store.set_stage("r1", "parse", path=db)
        store.set_stage("r1", "extract", path=db)
        store.finish_run("r1", "error", "ValueError: markdown gần như rỗng", path=db)

        run = store.get_run("r1", path=db)
        assert run["status"] == "error"
        assert run["stage"] == "extract"          # dừng ở đâu còn nguyên
        assert "ValueError" in run["error"]

    def test_status_la_khong_hop_le(self, db):
        store.new_run("r1", 1, "k", path=db)
        with pytest.raises(ValueError, match="không hợp lệ"):
            store.finish_run("r1", "xong_roi", path=db)

    def test_liet_ke_moi_nhat_truoc(self, db):
        for i in range(3):
            store.new_run(f"r{i}", 1, "k", path=db)
        assert len(store.runs(1, path=db)) == 3
        assert store.runs(1, limit=2, path=db).__len__() == 2

    def test_run_khong_ton_tai(self, db):
        assert store.get_run("khong-co", path=db) is None


class TestReapOrphans:
    def test_job_mo_coi_thanh_error(self, db):
        """Hàng đợi ở trong bộ nhớ: server tắt là job mất, để nguyên `running`
        thì UI hiện thanh tiến độ đứng im vĩnh viễn."""
        store.new_run("r1", 1, "k", path=db)                    # queued
        store.new_run("r2", 1, "k", path=db)
        store.start_run("r2", "x.log", path=db)                 # running
        store.new_run("r3", 1, "k", path=db)
        store.finish_run("r3", "completed", path=db)            # đã xong

        assert store.reap_orphans(path=db) == 2
        assert store.get_run("r1", path=db)["status"] == "error"
        assert store.get_run("r2", path=db)["status"] == "error"
        assert store.get_run("r3", path=db)["status"] == "completed"
        assert "server dừng giữa chừng" in store.get_run("r2", path=db)["error"]

    def test_chay_lai_khi_khong_co_gi_mo_coi(self, db):
        assert store.reap_orphans(path=db) == 0

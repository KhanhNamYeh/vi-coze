"""Chặn bốn bug đã xảy ra thật quanh tên collection và tên sheet.

Cả bốn có chung một dạng: MỘT giá trị được khai hoặc suy ra ở hai nơi, rồi hai
nơi lệch nhau mà không có gì báo. Truy vấn vẫn chạy, chỉ là hỏi nhầm collection
hoặc đọc nhầm sheet - kiểu hỏng không bao giờ tự lộ ra.
"""

from __future__ import annotations

import json

import pytest

from src.config import ROOT, ChunkCfg, KBConfig, KnowledgeCfg


@pytest.fixture(scope="module")
def cfg() -> KBConfig:
    c = KBConfig.load("sql")
    c.project = 1
    return c


class TestCollectionKhongConTemplate:
    """`{project}` phải được thay ở MỌI nơi đọc collection.

    Đã xảy ra: `COLLECTION` trong branch_sql/config.py giữ nguyên template nên
    Qdrant nhận tên chứa dấu ngoặc và trả 404 rất khó lần ra nguồn.
    """

    def test_hang_so_da_duoc_thay(self):
        from src.branch_sql.config import COLLECTION, SQL_COLLECTION

        assert "{project}" not in COLLECTION
        assert SQL_COLLECTION is None or "{project}" not in SQL_COLLECTION

    def test_knowledge_tra_ten_that(self, cfg):
        for k in cfg.knowledge:
            for p in k.projects:
                assert "{" not in k.collection_for(p)

    def test_studio_cung_phai_thay(self):
        """Knowledge tạo từ UI đi qua một đường khác - cũng phải format."""
        row_collection = "sqlp{project}__demo"
        assert row_collection.format(project=1) == "sqlp1__demo"


class TestCollectionOf:
    """Tra collection theo `doc_id` thay vì dùng hằng số.

    Đã xảy ra hai lần: `verify/integrity` và CLI `index/qdrant_store` đều dùng
    hằng `COLLECTION`, nên bộ SQL sample bị hỏi/ghi nhầm vào collection tài liệu.
    """

    def test_moi_bo_tri_thuc_ra_dung_collection_cua_no(self):
        from src.branch_sql.config import collection_of

        assert collection_of("mo_ta_bang_bds_new__docx", project=1) == "sqlp1__docs"
        assert collection_of("text2sql_testcase__xlsx", project=1) == "sqlp1__sql"

    def test_hai_bo_khong_dung_chung_collection(self):
        from src.branch_sql.config import collection_of

        docs = collection_of("mo_ta_bang_bds_new__docx", project=1)
        sql = collection_of("text2sql_testcase__xlsx", project=1)
        assert docs != sql, "SQL sample và tài liệu phải nằm ở hai collection"

    def test_doc_id_la_bao_loi_ro_rang(self):
        from src.branch_sql.config import collection_of

        with pytest.raises(ValueError, match="không bộ tri thức nào"):
            collection_of("khong_ton_tai__docx", project=1)

    def test_chi_khai_o_mot_noi(self):
        """`collection_of` chỉ được định nghĩa một lần. Hai bản là mời một bản
        lệch đi khi profile đổi."""
        hits = [
            p for p in (ROOT / "src" / "branch_sql").rglob("*.py")
            if "def collection_of(" in p.read_text(encoding="utf-8")
        ]
        assert [p.name for p in hits] == ["config.py"], f"khai ở nhiều nơi: {hits}"


class TestCachLyDuAn:
    def test_giao_tap_collection_hai_du_an_la_rong(self, cfg):
        by_project = {
            p: {k.collection_for(p) for k in cfg.knowledge_of(p)} for p in cfg.projects
        }
        a, b = (by_project[p] for p in cfg.projects[:2])
        assert not (a & b), f"hai dự án dùng chung collection: {a & b}"

    def test_chan_khai_chung_mot_kho_co_dinh(self):
        """Bộ tri thức nhiều dự án mà tên collection cố định thì profile phải
        không nạp được - nếu không, hai hộp đen đọc trúng cùng một kho."""
        with pytest.raises(ValueError, match="cố định"):
            KnowledgeCfg(id="x", source="a.docx", project=[1, 2],
                         collection="chung__sql", chunk=None)


class TestTenSheetChiKhaiMotNoi:
    """Đã xảy ra: `gold_parse` hardcode "from schema"/"Sheet2" trong khi profile
    khai ở `parse.sheets`. Excel đổi tên sheet thì chỉ sửa được một chỗ."""

    def test_gold_parse_doc_tu_profile(self):
        src = (ROOT / "src" / "branch_sql" / "eval" / "gold_parse.py").read_text(
            encoding="utf-8")
        body = src[src.index("OUTPUTS = ("):]
        assert "CFG.parse.sheets" in src or "_SHEETS" in body
        for hardcoded in ('"from schema"', '"Sheet2"'):
            assert hardcoded not in body, f"vẫn hardcode {hardcoded}"

    def test_profile_khai_du_hai_vai_tro(self, cfg):
        assert set(cfg.parse.sheets) >= {"dev", "test"}

    def test_sheet_khai_trong_profile_co_that_trong_excel(self, cfg):
        openpyxl = pytest.importorskip("openpyxl")
        src = cfg.raw_dir / "Text2SQL_testcase.xlsx"
        if not src.exists():
            pytest.skip("chưa có file testcase")
        wb = openpyxl.load_workbook(src, read_only=True)
        try:
            for role, sheet in cfg.parse.sheets.items():
                assert sheet in wb.sheetnames, (
                    f"parse.sheets['{role}']='{sheet}' không có trong Excel "
                    f"({', '.join(wb.sheetnames)})"
                )
        finally:
            wb.close()


class TestBoDoKhopExcel:
    def test_dev_va_test_sinh_ra_tu_dung_sheet(self, cfg):
        openpyxl = pytest.importorskip("openpyxl")
        src = cfg.raw_dir / "Text2SQL_testcase.xlsx"
        if not src.exists() or not (cfg.eval_dir / "dev.json").exists():
            pytest.skip("chưa có bộ đo")

        wb = openpyxl.load_workbook(src, read_only=True, data_only=True)
        try:
            counts = {
                role: sum(1 for r in wb[sheet].iter_rows(values_only=True)
                          if r and str(r[0] or "").strip()) - 1
                for role, sheet in cfg.parse.sheets.items()
            }
        finally:
            wb.close()

        for role in ("dev", "test"):
            got = len(json.loads((cfg.eval_dir / f"{role}.json").read_text(encoding="utf-8")))
            assert got == counts[role], (
                f"{role}.json có {got} dòng nhưng sheet "
                f"'{cfg.parse.sheets[role]}' có {counts[role]} - chạy lại gold_parse"
            )

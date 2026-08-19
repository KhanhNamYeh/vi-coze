"""Hợp đồng ranh giới extract -> link của nhánh SQL."""

from __future__ import annotations

from src.branch_sql.offline.extract.block_extract import SCHEMA_VERSION, build_ir, extract
from src.branch_sql.offline.extract.blocks import split as split_blocks
from src.branch_sql.offline.link.hierarchy import link
from src.config import ExtractCfg, RoleCfg

ROLES = {1: "section", 2: "table"}
CFG = ExtractCfg(
    enabled=True,
    heading_roles=ROLES,
    roles=[
        RoleCfg(role="table_meaning", match=[r"^Ý nghĩa\s*:"]),
        RoleCfg(role="column_intro", match=[r"^Chi tiết các cột\s*:"]),
        RoleCfg(role="relation_hint", match=[r"^Mối liên kết\s*:"]),
        RoleCfg(role="business_rule", match=[r"^Ghi chú\s*:"]),
    ],
)

MD = (
    "# Danh mục dùng chung\n\n"
    "## Bảng PRECINCT\n\n"
    "Ý nghĩa: Lưu thông tin phường/xã\n"
    "Chi tiết các cột:\n\n"
    "| Tên cột | Kiểu |\n| --- | --- |\n| ID | NUMBER |\n| CODE | VARCHAR2 |\n\n"
    "Mối liên kết:\n\n"
    "qua cột CODE\n\n"
    "Ghi chú: Dữ liệu khoảng 10000 dòng.\n\n"
    "## Bảng PROJECT\n\n"
    "Ý nghĩa: Lưu dự án\n"
)


def extracted() -> list[dict]:
    return extract(split_blocks(MD, heading_roles=ROLES), cfg=CFG)


def linked() -> dict:
    ir = build_ir(
        split_blocks(MD, heading_roles=ROLES),
        doc_id="d1",
        title="T",
        source_name="source.docx",
        cfg=CFG,
    )
    return link(ir)


class TestExtractDocLap:
    def test_chi_tao_structured_elements(self):
        forbidden = {"parent_id", "section", "table", "caption_of", "relations"}
        assert all(not forbidden.intersection(element) for element in extracted())

    def test_giu_noi_dung_bang_va_khoang_dong(self):
        table = next(e for e in extracted() if e["modality"] == "table")
        assert table["columns"] == ["Tên cột", "Kiểu"]
        assert table["rows"] == [["ID", "NUMBER"], ["CODE", "VARCHAR2"]]
        assert table["line_start"] < table["line_end"]

    def test_envelope_toi_thieu(self):
        ir = build_ir(
            split_blocks(MD, heading_roles=ROLES),
            doc_id="d1",
            title="T",
            source_name="source.docx",
            cfg=CFG,
        )
        assert set(ir) == {
            "schema_version",
            "doc_id",
            "title",
            "source_name",
            "warnings",
            "elements",
        }
        assert ir["schema_version"] == SCHEMA_VERSION == "1.0"
        assert ir["source_name"] == "source.docx"


class TestLinkDungCay:
    def test_link_moi_gan_parent_va_to_tien(self):
        elements = linked()["elements"]
        by_id = {e["id"]: e for e in elements}
        rule = next(e for e in elements if e.get("role") == "business_rule")
        assert by_id[rule["parent_id"]]["text"] == "Bảng PRECINCT"
        assert rule["section"] == "Danh mục dùng chung"
        assert rule["table"] == "Bảng PRECINCT"

    def test_heading_cha_con(self):
        elements = linked()["elements"]
        section = elements[0]
        table_heading = next(e for e in elements if e.get("role") == "table")
        assert section["parent_id"] is None
        assert table_heading["parent_id"] == section["id"]

    def test_ghep_nhan_dung_rieng_voi_text_sau(self):
        relation = next(e for e in linked()["elements"] if e.get("role") == "relation_hint")
        assert relation["text"] == "qua cột CODE"
        assert relation["line_start"] < relation["line_end"]

    def test_khong_tao_quan_he(self):
        """Ranh giới với `graph`: chặng này chỉ dựng cây, không diễn giải quan hệ."""
        assert "relations" not in linked()

    def test_nhan_dan_vao_bang_van_dung_rieng(self):
        """"Chi tiết các cột:" không bị nuốt vào bảng, vẫn là element text riêng
        nên nội dung của nó vẫn vào chunk."""
        elements = linked()["elements"]
        caption = next(e for e in elements if e.get("role") == "column_intro")
        assert caption["text"] == "" and caption["label"].startswith("Chi tiết các cột")

    def test_link_khong_sua_extract_input(self):
        ir = build_ir(
            split_blocks(MD, heading_roles=ROLES),
            doc_id="d1",
            source_name="source.docx",
            cfg=CFG,
        )
        original = [dict(e) for e in ir["elements"]]
        link(ir)
        assert ir["elements"] == original

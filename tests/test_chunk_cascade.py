"""Kiểm chứng chunk/table_chunker — thang cắt, ngân sách, ngữ cảnh.

Mọi test dựng ChunkCfg tại chỗ và đo bằng `char`, không dùng profile và không
nạp tokenizer: thang cắt phải đúng độc lập với đơn vị đo và với model embed.
"""

from __future__ import annotations

import pytest

from src.branch_sql.offline.chunk import table_chunker as tc
from src.config import BudgetCfg, ChunkCfg, ContextCfg, FilterCfg, InheritCfg, SplitRule


def heading_only(**budget) -> ChunkCfg:
    """Kịch bản của profile SQL: cắt thuần theo `##`, không quan tâm độ dài."""
    return ChunkCfg(
        split_on=[SplitRule(by="heading", level=2)],
        budget=BudgetCfg(unit="char", **{"max": 100, "min": 10, "on_overflow": "keep", **budget}),
        filter=FilterCfg(),
        context=ContextCfg(),
    )


def cfg(**budget) -> ChunkCfg:
    return ChunkCfg(
        split_on=[
            SplitRule(by="heading", level=2),
            SplitRule(by="table_row", group=2, repeat_header=True),
            SplitRule(by="length"),
        ],
        budget=BudgetCfg(unit="char", **{"max": 400, "min": 10, **budget}),
        filter=FilterCfg(),
        context=ContextCfg(inherit=InheritCfg(from_roles=["table_meaning"], max_chars=50)),
    )


def heading(id_, text):
    return {"id": id_, "modality": "heading", "level": 2, "role": "table", "text": text,
            "section": "Nhóm", "line_start": 1, "line_end": 1}


def text(id_, body, *, role=None, owner="Bảng T"):
    return {"id": id_, "modality": "text", "role": role, "label": "", "text": body,
            "table": owner, "section": "Nhóm", "line_start": 2, "line_end": 2}


def table(id_, rows, *, owner="Bảng T"):
    body = "| Tên cột | Kiểu |\n| --- | --- |\n" + "\n".join(f"| {r[0]} | {r[1]} |" for r in rows)
    return {"id": id_, "modality": "table", "text": body, "columns": ["Tên cột", "Kiểu"],
            "rows": [list(r) for r in rows], "table": owner, "section": "Nhóm",
            "line_start": 3, "line_end": 3 + len(rows)}


ROWS = [(f"COT_{i}", "VARCHAR2") for i in range(6)]


class TestTableSlices:
    RULE = SplitRule(by="table_row", group=2, repeat_header=True)

    def test_cat_theo_nhom_hang_va_lap_header(self):
        pieces = tc.table_slices(table("el_1", ROWS), self.RULE)
        assert len(pieces) == 3
        assert all(p.startswith("| Tên cột | Kiểu |") for p in pieces)
        assert "COT_2" in pieces[1] and "COT_0" not in pieces[1]

    def test_khong_lap_header_khi_tat(self):
        rule = SplitRule(by="table_row", group=2, repeat_header=False)
        pieces = tc.table_slices(table("el_1", ROWS), rule)
        assert pieces[0].startswith("| Tên cột")
        assert not pieces[1].startswith("| Tên cột")

    def test_escape_dau_ngan_cot(self):
        el = table("el_1", [("A|B", "NUMBER")])
        assert r"A\|B" in tc.table_slices(el, self.RULE)[0]

    def test_bang_khong_co_hang_giu_nguyen_markdown(self):
        el = {"id": "el_1", "modality": "table", "text": "| a |", "columns": ["a"], "rows": []}
        assert tc.table_slices(el, self.RULE) == ["| a |"]


class TestThangCat:
    def test_vua_ngan_sach_thi_mot_chunk(self):
        group = [heading("el_1", "Bảng T"), text("el_2", "ngắn")]
        assert len(tc.split_unit(group, cfg())) == 1

    def test_vuot_tran_thi_xuong_bac_table_row(self):
        group = [heading("el_1", "Bảng T"), table("el_2", ROWS)]
        parts = tc.split_unit(group, cfg(max=120))
        assert len(parts) == 3
        assert all("| Tên cột" in p for p, _ in parts)

    def test_on_overflow_keep_thi_khong_cat(self):
        group = [heading("el_1", "Bảng T"), table("el_2", ROWS)]
        assert len(tc.split_unit(group, cfg(max=50, on_overflow="keep"))) == 1

    def test_modality_atomic_khong_bi_cat(self):
        c = cfg(max=120)
        c.filter.atomic_modalities = ["table"]
        group = [heading("el_1", "Bảng T"), table("el_2", ROWS)]
        # không cắt theo hàng nữa, rơi xuống bậc length
        assert all("| Tên cột | Kiểu |" not in p for p, _ in tc.split_unit(group, c)[1:])

    def test_bac_length_la_chot_chan_cuoi(self):
        group = [heading("el_1", "Bảng T"), text("el_2", "câu dài. " * 200)]
        parts = tc.split_unit(group, cfg(max=200))
        assert len(parts) > 1 and all(len(p) <= 200 for p, _ in parts)


class TestSplit:
    IR = {
        "doc_id": "d1",
        "title": "Tài liệu T",
        "source_name": "t.docx",
        "elements": [
            heading("el_1", "Bảng T"),
            text("el_2", "Lưu thông tin phường xã", role="table_meaning"),
            table("el_3", ROWS),
        ],
    }

    def test_breadcrumb_dung_dau_chunk(self):
        doc = tc.split(self.IR, cfg=cfg())[0]
        assert doc.page_content.startswith("Tài liệu T > Nhóm > Bảng T")

    def test_tat_breadcrumb(self):
        c = cfg()
        c.context.breadcrumb.enabled = False
        assert not tc.split(self.IR, cfg=c)[0].page_content.startswith("Tài liệu T")

    def test_manh_sau_thua_huong_ngu_canh(self):
        docs = tc.split(self.IR, cfg=cfg(max=120))
        assert len(docs) > 1
        assert "Lưu thông tin phường xã" in docs[1].page_content
        assert docs[1].metadata["part"] == "2/3"

    def test_chunk_id_theo_noi_dung_khong_theo_vi_tri(self):
        """Chèn một bảng ở đầu tài liệu không được đổi ID của bảng phía sau."""
        pick = lambda docs: next(d.metadata["chunk_id"] for d in docs  # noqa: E731
                                 if "el_3" in d.metadata["element_ids"])
        first = pick(tc.split(self.IR, cfg=cfg()))
        moved = {**self.IR, "elements": [
            heading("el_9", "Bảng A"),
            text("el_10", "bảng chèn thêm", owner="Bảng A"),
            *self.IR["elements"],
        ]}
        assert pick(tc.split(moved, cfg=cfg())) == first

    def test_giu_duong_ve_ir(self):
        meta = tc.split(self.IR, cfg=cfg())[0].metadata
        assert meta["element_ids"] == ["el_1", "el_2", "el_3"]
        assert meta["line_start"] == 1 and meta["line_end"] == 9

    def test_khong_co_heading_don_vi_thi_rong(self):
        ir = {**self.IR, "elements": [{"id": "el_1", "modality": "text", "text": "x"}]}
        assert tc.split(ir, cfg=cfg()) == []


class TestCheck:
    def test_canh_bao_vuot_tran(self):
        docs = tc.split(TestSplit.IR, cfg=cfg(max=120, on_overflow="keep"))
        assert any("vượt trần" in w for w in tc.check(docs, cfg=cfg(max=120)))

    def test_canh_bao_duoi_san(self):
        docs = tc.split(TestSplit.IR, cfg=cfg())
        assert any("dưới sàn" in w for w in tc.check(docs, cfg=cfg(max=10000, min=9999)))

    def test_khong_chunk_nao(self):
        assert tc.check([], cfg=cfg())[0].startswith("0 chunk")


class TestChiCatTheoHeading:
    """Kịch bản mặc định của profile SQL."""

    def test_moi_heading_mot_chunk_du_vuot_tran(self):
        docs = tc.split(TestSplit.IR, cfg=heading_only())
        assert len(docs) == 1
        assert docs[0].metadata["part"] == "1/1"
        assert len(docs[0].page_content) > 100  # vượt trần mà vẫn không bị cắt

    def test_hai_don_vi_ra_hai_chunk(self):
        ir = {**TestSplit.IR, "elements": [
            *TestSplit.IR["elements"],
            heading("el_9", "Bảng A"),
            text("el_10", "nội dung A", owner="Bảng A"),
        ]}
        assert len(tc.split(ir, cfg=heading_only())) == 2

    def test_van_canh_bao_khi_vuot_tran(self):
        """Không cắt, nhưng phải nói cho biết chunk nào vượt giới hạn embedder."""
        docs = tc.split(TestSplit.IR, cfg=heading_only())
        assert any("vượt trần" in w for w in tc.check(docs, cfg=heading_only()))


class TestConfig:
    def test_descend_thi_bac_cuoi_phai_la_length(self):
        with pytest.raises(ValueError, match=r"phải\s+là .length."):
            ChunkCfg(
                split_on=[SplitRule(by="heading", level=2)],
                budget=BudgetCfg(on_overflow="descend"),
            )

    def test_keep_thi_khong_can_bac_length(self):
        cfg_ = ChunkCfg(
            split_on=[SplitRule(by="heading", level=2)],
            budget=BudgetCfg(on_overflow="keep"),
        )
        assert [r.by for r in cfg_.split_on] == ["heading"]

    def test_min_phai_nho_hon_max(self):
        with pytest.raises(ValueError, match="min phải nhỏ hơn"):
            BudgetCfg(max=100, min=100)

"""Kiểm chứng parse/pdf_parse - đọc DoclingDocument, không cần cài docling.

Item giả chỉ mang đúng những thuộc tính mà `pdf_parse` đọc: `label`, `text`,
`marker`. Mọi ca dưới đây lấy từ output thật của docling trên
`Mô tả bảng BĐS (NEW).pdf`.

Điểm cần chứng minh: cấp bậc suy từ SỐ THỨ TỰ của tài liệu, không phụ thuộc việc
docling gán nhãn đúng hay sai. Docling nhận nhầm ba tên bảng thành gạch đầu dòng
và gán mọi tiêu đề level=1; tin vào nhãn thì mất 3/18 bảng.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.branch_sql.offline.parse.pdf_parse import heading_of, render


@dataclass
class Item:
    label: str
    text: str = ""
    marker: str = ""


class FakeDoc:
    """Đủ để `render` chạy: `iterate_items` và bảng tự xuất markdown."""

    def __init__(self, items):
        self._items = items

    def iterate_items(self):
        return ((it, 0) for it in self._items)


class Table:
    label = "table"

    def __init__(self, md: str):
        self._md = md

    def export_to_markdown(self, doc):  # noqa: ARG002
        return self._md


HEAD = "| Tên cột | Kiểu |\n| --- | --- |\n| A | NUMBER |"
CONT = "| B | VARCHAR2 |\n| --- | --- |\n| C | NUMBER |"


class TestCapBacTheoSo:
    def test_so_mot_cap_la_nhom(self):
        assert heading_of(Item("section_header", "1. Danh mục dùng chung")) == (1, "Danh mục dùng chung")

    def test_so_hai_cap_la_bang(self):
        assert heading_of(Item("section_header", "1.1. Bảng PRECINCT")) == (2, "Bảng PRECINCT")

    def test_tieu_de_bi_doc_nham_thanh_gach_dau_dong(self):
        """Ca thật: 3.1, 6.1, 6.2 - docling để số ở `marker`, text mất số."""
        it = Item("list_item", "Bảng V_BDS_NEW_SUB_SHOP", marker="3.1.")
        assert heading_of(it) == (2, "Bảng V_BDS_NEW_SUB_SHOP")

    def test_gach_dau_dong_thuong_khong_thanh_tieu_de(self):
        """Thân bài cũng được docling đánh số, nhưng luôn một cấp."""
        it = Item("list_item", "Liên kết với các bảng khác qua cột CODE.", marker="5.")
        assert heading_of(it) is None

    def test_tieu_de_khong_danh_so_khong_phai_tieu_de(self):
        assert heading_of(Item("section_header", "MỤC LỤC")) is None

    def test_doan_van_thuong(self):
        assert heading_of(Item("text", "Ý nghĩa của bảng: lưu quyền")) is None


class TestRender:
    def test_dung_dau_thang_theo_do_sau(self):
        md = render(FakeDoc([
            Item("section_header", "1. Nhóm"),
            Item("section_header", "1.1. Bảng A"),
        ]))
        assert "# Nhóm" in md and "## Bảng A" in md

    def test_bo_bia_va_muc_luc_truoc_tieu_de_dau_tien(self):
        md = render(FakeDoc([
            Item("section_header", "MỤC LỤC"),
            Item("document_index", "1. Danh mục....... 1"),
            Item("section_header", "1. Nhóm"),
        ]))
        assert "MỤC LỤC" not in md and "......." not in md
        assert "# Nhóm" in md

    def test_noi_bang_bi_ngat_trang(self):
        md = render(FakeDoc([Item("section_header", "1.1. Bảng A"), Table(HEAD), Table(CONT)]))
        rows = [l for l in md.splitlines() if l.startswith("|")]
        assert sum(1 for l in rows if "---" in l) == 1, "chỉ còn một dòng ngăn cách"
        assert "| B | VARCHAR2 |" in rows and "| C | NUMBER |" in rows

    def test_bang_cach_nhau_boi_van_ban_thi_khong_noi(self):
        md = render(FakeDoc([
            Item("section_header", "1.1. Bảng A"), Table(HEAD),
            Item("text", "Ghi chú: x"),
            Item("section_header", "1.2. Bảng B"), Table(CONT),
        ]))
        assert sum(1 for l in md.splitlines() if l.startswith("|") and "---" in l) == 2

    def test_bo_ky_tu_gach_dau_dong_con_sot(self):
        """Sót `●` thì nhãn không còn ở đầu dòng và `extract` mất role."""
        md = render(FakeDoc([
            Item("section_header", "1. Nhóm"),
            Item("list_item", "● Mối liên kết:\n-Liên kết qua cột CODE."),
        ]))
        assert "Mối liên kết:" in md
        assert "●" not in md and "-Liên kết" not in md

    def test_tai_lieu_khong_co_tieu_de_danh_so_thi_rong(self):
        assert render(FakeDoc([Item("text", "chỉ có văn bản")])).strip() == ""

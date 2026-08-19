"""Bất biến của chặng `parse`: bản .docx và bản .pdf phải ra cùng một cấu trúc.

Số block được phép lệch, cấu trúc thì không. Đây là chỉ số nghiệm thu cho nhánh
PDF — hư hại do docling đọc theo TRANG chỉ lộ ra khi so hai định dạng với nhau.

Hai chuỗi markdown dưới đây là cùng một mục, khác nhau đúng những gì hai loader
thật khác nhau — đo trên `Mô tả bảng BĐS (NEW)`:

    ① vị trí bảng   markitdown giữ bảng tại chỗ; docling dồn bảng xuống cuối mục
    ② dòng trắng    markitdown chẻ text làm hai khối; docling để liền một khối

Dựng markdown trong bộ nhớ chứ không đọc `data/processed/`: bất biến phải đúng
với LUẬT, không phụ thuộc lần chạy pipeline gần nhất.
"""

from __future__ import annotations

from src.branch_sql.offline.extract.blocks import count_roles, split

ROLES = {1: "section", 2: "table"}

TABLE = "| Tên cột | Kiểu |\n| --- | --- |\n| ID | NUMBER |\n| CODE | VARCHAR2 |"

# markitdown: bảng nằm đúng chỗ của nó, dòng trắng chẻ text làm hai khối.
DOCX = (
    "# Danh mục dùng chung\n\n"
    "## Bảng PRECINCT\n\n"
    "Ý nghĩa của bảng: Lưu thông tin phường/xã\n"
    "Chi tiết các cột trong bảng:\n\n"
    f"{TABLE}\n\n"
    "Mối liên kết:\n"
    "Liên kết qua cột CODE\n"
    "Ghi chú:\n"
    "Dữ liệu khoảng 168 dòng.\n"
)

# docling: đọc theo trang nên bảng bị dồn xuống cuối mục, text liền một khối.
PDF = (
    "# Danh mục dùng chung\n\n"
    "## Bảng PRECINCT\n\n"
    "Ý nghĩa của bảng: Lưu thông tin phường/xã\n"
    "Chi tiết các cột trong bảng:\n"
    "Mối liên kết:\n"
    "Liên kết qua cột CODE\n"
    "Ghi chú:\n"
    "Dữ liệu khoảng 168 dòng.\n\n"
    f"{TABLE}\n"
)


def blocks_of(md: str):
    return split(md, heading_roles=ROLES)


class TestCauTrucHoiTu:
    def test_cung_so_heading_theo_vai_tro(self):
        assert count_roles(blocks_of(DOCX)) == count_roles(blocks_of(PDF))

    def test_cung_so_bang(self):
        n = [sum(1 for b in blocks_of(md) if b.type == "table") for md in (DOCX, PDF)]
        assert n == [1, 1]

    def test_cung_ten_heading_theo_thu_tu(self):
        names = [
            [b.text for b in blocks_of(md) if b.type == "heading"] for md in (DOCX, PDF)
        ]
        assert names[0] == names[1] == ["Danh mục dùng chung", "Bảng PRECINCT"]

    def test_khong_dinh_dang_nao_co_canh_bao_cau_truc(self):
        from src.branch_sql.offline.extract.blocks import check

        for md in (DOCX, PDF):
            assert check(blocks_of(md), roles=ROLES) == []


class TestSoBlockDuocPhepLech:
    """Dòng trắng đổi cách gom block. Đó là khác biệt thật và không phải lỗi —
    nó KHÔNG ảnh hưởng tới cấu trúc, nên bất biến ở trên vẫn giữ."""

    def test_docling_gom_text_lien_mot_khoi(self):
        para = [
            sum(1 for b in blocks_of(md) if b.type == "paragraph") for md in (DOCX, PDF)
        ]
        assert para == [2, 1]

    def test_moi_block_van_tro_dung_dong_trong_md(self):
        for md in (DOCX, PDF):
            lines = md.splitlines()
            for b in blocks_of(md):
                span = "\n".join(lines[b.line_start - 1 : b.line_end])
                assert b.text.splitlines()[0] in span

"""Kiểm chứng extract/blocks và extract/block_extract.

Điểm cần chứng minh: logic không dính vào quy ước của một bộ tài liệu nào. Nên
phần lớn test ở đây chạy trên tài liệu format KHÁC hẳn `sql.json` - heading khác
cấp, nhãn tiếng Anh, bảng không có dòng ngăn cách.
"""

from __future__ import annotations

from src.branch_sql.offline.extract.block_extract import extract, parse_table, parse_text
from src.branch_sql.offline.extract.blocks import Block, check, count_roles, split
from src.config import ExtractCfg, RoleCfg

VN_ROLES = ExtractCfg(
    enabled=True,
    roles=[
        RoleCfg(role="relation_hint", match=[r"^Mối liên kết\s*:"]),
        RoleCfg(role="business_rule", match=[r"^Ghi chú\s*:"]),
    ],
)

# Bộ tài liệu tưởng tượng: nhãn tiếng Anh, bảng ở cấp ###
EN_ROLES = ExtractCfg(
    enabled=True,
    roles=[
        RoleCfg(role="relation_hint", match=[r"^Relations?\s*:"]),
        RoleCfg(role="business_rule", match=[r"^Notes?\s*:", r"^Remarks?\s*:"]),
    ],
)


class TestSplit:
    def test_gom_dong_lien_nhau(self):
        md = "# A\n\ndòng 1\ndòng 2\n\n| x | y |\n| --- | --- |\n| 1 | 2 |\n"
        blocks = split(md, heading_roles={1: "section"})
        assert [b.type for b in blocks] == ["heading", "paragraph", "table"]

    def test_khoi_code_khong_bi_doc_nham_thanh_bang(self):
        """Ca mà tách bằng regex sẽ sai: dòng trông như bảng nằm trong khối code."""
        md = "```\n| A | B |\n| --- | --- |\n```\n"
        blocks = split(md, heading_roles={})
        assert [b.type for b in blocks] == ["code"]

    def test_heading_kieu_gach_duoi(self):
        """`===` cũng là heading cấp 1 theo CommonMark."""
        blocks = split("Tiêu đề\n=======\n", heading_roles={1: "section"})
        assert blocks[0].type == "heading"
        assert blocks[0].level == 1 and blocks[0].role == "section"

    def test_heading_luon_dung_mot_minh(self):
        blocks = split("# A\n## B\n## C\n", heading_roles={})
        assert len(blocks) == 3
        assert [b.level for b in blocks] == [1, 2, 2]

    def test_heading_bo_dau_thang_va_giu_cap(self):
        b = split("#### Sâu\n", heading_roles={})[0]
        assert b.level == 4 and b.text == "Sâu"

    def test_vai_tro_lay_tu_config_khong_hardcode(self):
        """Tài liệu dùng ### cho bảng thì chỉ đổi config."""
        blocks = split("### T\n", heading_roles={3: "table"})
        assert blocks[0].role == "table"
        blocks = split("### T\n", heading_roles={2: "table"})
        assert blocks[0].role is None

    def test_so_dong_de_truy_nguoc(self):
        blocks = split("# A\n\n\nnội dung\n", heading_roles={})
        assert blocks[0].line_start == 1
        assert blocks[1].line_start == 4

    def test_id_lien_tuc_theo_thu_tu_doc(self):
        """Thứ tự đọc là thứ tự mảng - không có trường `order` nào lưu lại nữa."""
        blocks = split("# A\n\nx\n\n# B\n", heading_roles={})
        assert [b.id for b in blocks] == ["block_1", "block_2", "block_3"]
        assert not hasattr(blocks[0], "order")

    def test_danh_sach_khong_thanh_paragraph(self):
        assert split("- một\n- hai\n", heading_roles={})[0].type == "list"

    def test_tai_lieu_rong(self):
        assert split("", heading_roles={}) == []


class TestCheck:
    """Cấu trúc hỏng phải lộ ra ở parse, không để chunking cắt sai rồi mới biết."""

    ROLES = {1: "section", 2: "table"}

    def test_tai_lieu_du_cau_truc_thi_khong_canh_bao(self):
        blocks = split("# Nhóm\n\n## Bảng A\n\nnội dung\n", heading_roles=self.ROLES)
        assert check(blocks, roles=self.ROLES) == []

    def test_thieu_han_mot_vai_tro(self):
        """Ca thật: restructure() không nâng được tên bảng lên `##`."""
        blocks = split("# Nhóm\n\nnội dung\n", heading_roles=self.ROLES)
        assert any("'table'" in w for w in check(blocks, roles=self.ROLES))

    def test_heading_lac_cap(self):
        blocks = split("# Nhóm\n\n## Bảng A\n\n#### Lạc\n", heading_roles=self.ROLES)
        assert any("[4]" in w for w in check(blocks, roles=self.ROLES))

    def test_tai_lieu_rong(self):
        assert check([], roles=self.ROLES) == ["0 block - tài liệu rỗng"]

    def test_dem_theo_vai_tro_khong_dem_theo_cap(self):
        blocks = split("# A\n\n## B\n\n## C\n\n#### D\n", heading_roles=self.ROLES)
        assert count_roles(blocks) == {"section": 1, "table": 2}


class TestParseTable:
    def _blk(self, text: str) -> Block:
        return Block(id="b", type="table", text=text, line_start=1, line_end=1)

    def test_co_dong_ngan_cach(self):
        t = parse_table(self._blk("| A | B |\n| --- | --- |\n| 1 | 2 |"))
        assert t["columns"] == ["A", "B"]
        assert t["rows"] == [["1", "2"]]

    def test_bo_dau_nhan_manh_o_tieu_de(self):
        t = parse_table(self._blk("| **A** | **B** |\n| --- | --- |\n| 1 | 2 |"))
        assert t["columns"] == ["A", "B"]

    def test_giu_nguyen_khi_tat_strip(self):
        t = parse_table(self._blk("| **A** |\n| --- |\n| 1 |"), strip_emphasis=False)
        assert t["columns"] == ["**A**"]

    def test_thieu_dong_ngan_cach_thi_khong_phai_bang(self):
        """Theo GFM, không có `|---|` thì đó là đoạn văn chứ không phải bảng."""
        t = parse_table(self._blk("| 1 | 2 |\n| 3 | 4 |"))
        assert t["columns"] == [] and t["rows"] == []

    def test_dong_thieu_o_duoc_dem_cho_bang_tieu_de(self):
        """GFM quy định hàng ngắn hơn tiêu đề thì đệm ô rỗng."""
        t = parse_table(self._blk("| A | B |\n| --- | --- |\n| 1 |"))
        assert t["rows"] == [["1", ""]]

    def test_dau_gach_dung_duoc_escape_trong_o(self):
        """Ca mà tự tách theo dấu `|` sẽ cắt nhầm."""
        t = parse_table(self._blk("| A | B |\n| --- | --- |\n| x \\| y | 2 |"))
        assert t["rows"] == [["x | y", "2"]]

    def test_dong_ngan_cach_can_le(self):
        t = parse_table(self._blk("| A | B |\n|:---|---:|\n| 1 | 2 |"))
        assert t["columns"] == ["A", "B"]


class TestParseText:
    def _blk(self, text: str) -> Block:
        return Block(id="b", type="paragraph", text=text, line_start=10, line_end=13)

    def test_nhan_cung_dong_voi_noi_dung(self):
        segs = parse_text(self._blk("Mối liên kết: qua cột CODE"), VN_ROLES.roles)
        assert segs[0]["role"] == "relation_hint"
        assert segs[0]["text"] == "qua cột CODE"

    def test_nhan_dung_rieng_noi_dung_dong_sau(self):
        segs = parse_text(self._blk("Mối liên kết:\nqua cột CODE"), VN_ROLES.roles)
        assert segs[0]["text"] == "qua cột CODE"

    def test_cat_mot_block_thanh_nhieu_role(self):
        """parse gom 4 dòng thành 1 block; extract phải cắt lại theo nhãn."""
        segs = parse_text(
            self._blk("Mối liên kết:\nqua cột CODE\nGhi chú:\nnhớ lọc quyền"), VN_ROLES.roles
        )
        assert [s["role"] for s in segs] == ["relation_hint", "business_rule"]
        assert segs[1]["text"] == "nhớ lọc quyền"

    def test_khong_khop_nhan_nao_thi_role_null(self):
        segs = parse_text(self._blk("một đoạn bình thường"), VN_ROLES.roles)
        assert len(segs) == 1 and segs[0]["role"] is None

    def test_khong_khai_role_nao_van_chay(self):
        segs = parse_text(self._blk("Mối liên kết: x"), [])
        assert segs[0]["role"] is None
        assert segs[0]["text"] == "Mối liên kết: x"

    def test_so_dong_tro_dung_vi_tri(self):
        segs = parse_text(self._blk("Mối liên kết:\nx\nGhi chú:\ny"), VN_ROLES.roles)
        assert segs[0]["line_start"] == 10
        assert segs[1]["line_start"] == 12

    def test_khoang_dong_phu_ca_nhan_lan_noi_dung(self):
        """Hồi quy: nhãn đứng riêng thì nội dung ở dòng SAU.

        Luật cũ tính như thể nội dung bắt đầu ngay tại dòng nhãn, nên khoảng
        dòng của đoạn không chứa lấy một chữ nào của chính nó - 2/3 phần tử
        text của bộ tài liệu thật bị sai.
        """
        # dòng 10 "Mối liên kết:" | 11 "x" | 12 "Ghi chú:" | 13 "y" | 14 "z"
        segs = parse_text(self._blk("Mối liên kết:\nx\nGhi chú:\ny\nz"), VN_ROLES.roles)
        assert (segs[0]["line_start"], segs[0]["line_end"]) == (10, 11)
        assert (segs[1]["line_start"], segs[1]["line_end"]) == (12, 14)

    def test_nhan_cung_dong_thi_khong_lan_sang_dong_sau(self):
        segs = parse_text(self._blk("Mối liên kết: x\nGhi chú: y"), VN_ROLES.roles)
        assert (segs[0]["line_start"], segs[0]["line_end"]) == (10, 10)
        assert (segs[1]["line_start"], segs[1]["line_end"]) == (11, 11)

    def test_nhan_khong_co_noi_dung_chi_chiem_dong_cua_no(self):
        """Nội dung nằm ở block khác; `link.caption_of` mới là chặng ghép."""
        segs = parse_text(self._blk("Ý nghĩa: có\nMối liên kết:"), VN_ROLES.roles)
        last = segs[-1]
        assert last["label"] == "Mối liên kết:" and last["text"] == ""
        assert (last["line_start"], last["line_end"]) == (11, 11)

    def test_khoang_dong_luon_chua_text_cua_chinh_no(self):
        """Bất biến: cắt `.md` theo line_start/line_end phải ra được text."""
        md_lines = ["Ý nghĩa: đầu tiên", "Mối liên kết:", "qua cột CODE", "và cột ID",
                    "Ghi chú:", "nhớ lọc quyền"]
        blk = Block(id="b", type="paragraph", text="\n".join(md_lines),
                    line_start=1, line_end=len(md_lines))
        for seg in parse_text(blk, VN_ROLES.roles):
            span = "\n".join(md_lines[seg["line_start"] - 1 : seg["line_end"]])
            for line in seg["text"].splitlines():
                assert line in span, f"{seg['role']}: {line!r} nằm ngoài khoảng dòng"


class TestTaiLieuKhacQuyUoc:
    """Cùng một code, bộ tài liệu tiếng Anh dùng ### cho bảng."""

    MD = (
        "# Catalog\n\n"
        "### Table CUSTOMER\n\n"
        "Stores customer records.\n\n"
        "| Column | Type |\n| --- | --- |\n| ID | NUMBER |\n\n"
        "Relations: joined via ID\n"
        "Note: soft-deleted rows excluded\n"
    )

    def test_chay_duoc_khong_sua_code(self):
        blocks = split(self.MD, heading_roles={1: "section", 3: "table"})
        els = extract(blocks, cfg=EN_ROLES)

        heads = [e for e in els if e["modality"] == "heading"]
        assert [h["role"] for h in heads] == ["section", "table"]

        table = next(e for e in els if e["modality"] == "table")
        assert table["columns"] == ["Column", "Type"]
        assert table["rows"] == [["ID", "NUMBER"]]

        roles = [e["role"] for e in els if e["modality"] == "text"]
        assert "relation_hint" in roles and "business_rule" in roles

    def test_khong_khai_role_van_tach_duoc_bang(self):
        blocks = split(self.MD, heading_roles={1: "section", 3: "table"})
        els = extract(blocks, cfg=ExtractCfg(enabled=True))
        assert any(e["modality"] == "table" and e["columns"] for e in els)
        assert all(e.get("role") is None for e in els if e["modality"] == "text")

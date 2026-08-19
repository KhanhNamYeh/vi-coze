"""Kiểm chứng link/hierarchy.

Hai điểm cần chứng minh:

1. Chặng này KHÔNG có config và KHÔNG biết vai trò nào tên là gì, nên nó phải
   chạy đúng trên tài liệu tiếng Anh, nhãn khác, vai trò heading đặt tên khác —
   không sửa một dòng nào. Phần lớn test ở đây dùng tài liệu tiếng Anh vì lý do đó.
2. Bản docx và bản pdf của CÙNG một tài liệu phải hội tụ: docling xếp phần tử
   theo thứ tự khác, nên cây bám vào cấp heading chứ không bám vị trí kề nhau.
"""

from __future__ import annotations

from src.branch_sql.offline.link.hierarchy import (
    attach_hierarchy,
    check,
    link,
    merge_standalone_labels,
)


def heading(id_, text, *, parent=None, level=2, role="table"):
    return {"id": id_, "parent_id": parent, "modality": "heading", "level": level,
            "role": role, "text": text}


def text(id_, body, *, parent=None, label="", role=None, line_end=1):
    return {"id": id_, "parent_id": parent, "modality": "text", "role": role,
            "label": label, "text": body, "line_end": line_end}


def table(id_, *, parent=None, columns=("Column", "Type"), label=None, body="| Column | Type |"):
    el = {"id": id_, "parent_id": parent, "modality": "table", "text": body,
          "columns": list(columns), "rows": []}
    if label is not None:
        el["label"] = label
    return el


class TestAttachHierarchy:
    def test_cap_nong_hon_dong_cap_sau_lai(self):
        els = attach_hierarchy([
            heading("el_1", "Group A", level=1, role="section"),
            heading("el_2", "Table X", level=2),
            text("el_3", "body"),
            heading("el_4", "Group B", level=1, role="section"),
            text("el_5", "body"),
        ])
        by_id = {e["id"]: e for e in els}
        assert by_id["el_1"]["parent_id"] is None
        assert by_id["el_2"]["parent_id"] == "el_1"
        assert by_id["el_3"]["parent_id"] == "el_2"
        # el_4 cùng cấp với el_1 nên đóng cả el_1 lẫn el_2
        assert by_id["el_4"]["parent_id"] is None
        assert by_id["el_5"]["parent_id"] == "el_4"

    def test_gan_ten_to_tien_theo_vai_tro(self):
        els = attach_hierarchy([
            heading("el_1", "Group A", level=1, role="section"),
            heading("el_2", "Table X", level=2, role="table"),
            text("el_3", "body"),
        ])
        el = els[-1]
        assert el["section"] == "Group A"
        assert el["table"] == "Table X"

    def test_vai_tro_dat_ten_gi_cung_chay(self):
        """Không có `if role == "table"` nào trong chặng này.

        Hồ sơ khác đặt tên vai trò là `chapter`/`entity` thì tên tổ tiên gắn theo
        đúng tên đó, không cần sửa code hay khai thêm config.
        """
        els = attach_hierarchy([
            heading("el_1", "Ch. 1", level=1, role="chapter"),
            heading("el_2", "Customer", level=2, role="entity"),
            text("el_3", "body"),
        ])
        el = els[-1]
        assert el["chapter"] == "Ch. 1" and el["entity"] == "Customer"
        assert "table" not in el and "section" not in el

    def test_khong_sua_input(self):
        src = [
            heading("el_1", "Group A", level=1, role="section"),
            text("el_2", "body"),
        ]
        out = attach_hierarchy(src)
        assert "section" not in src[1] and "parent_id" not in src[1] or src[1]["parent_id"] is None
        assert out[1]["section"] == "Group A" and out[1]["parent_id"] == "el_1"

    def test_heading_khong_co_role_van_lam_cha(self):
        els = attach_hierarchy([
            heading("el_1", "Untitled", level=1, role=None),
            text("el_2", "body"),
        ])
        assert els[1]["parent_id"] == "el_1"

    def test_noi_dung_truoc_heading_dau_tien_khong_co_cha(self):
        els = attach_hierarchy([
            text("el_1", "lời mở đầu"),
            heading("el_2", "Table X"),
        ])
        assert els[0]["parent_id"] is None


class TestMergeStandaloneLabels:
    def test_ghep_nhan_voi_text_ngay_sau(self):
        els = merge_standalone_labels([
            text("el_1", "", parent="h", label="Relations:", role="relation_hint"),
            text("el_2", "joins on CODE", parent="h", line_end=9),
        ])
        assert len(els) == 1
        assert els[0]["id"] == "el_1"                    # giữ ID của nhãn
        assert els[0]["text"] == "joins on CODE"
        assert els[0]["line_end"] == 9                   # khoảng dòng nới ra

    def test_khong_ghep_qua_cha_khac(self):
        els = merge_standalone_labels([
            text("el_1", "", parent="h1", label="Relations:"),
            text("el_2", "joins on CODE", parent="h2"),
        ])
        assert len(els) == 2 and els[0]["text"] == ""

    def test_khong_nuot_nhan_dan_vao_bang(self):
        """"Chi tiết các cột:" dẫn vào một bảng, không phải vào text.

        Nuốt vào thì nhãn dính hàng tiêu đề và hỏng cú pháp markdown. Để riêng
        thì nó vẫn vào chunk thành một dòng - đúng thứ RAG cần.
        """
        els = merge_standalone_labels([
            text("el_1", "", parent="h", label="Columns:", role="column_intro"),
            table("el_2", parent="h"),
        ])
        assert len(els) == 2 and els[0]["text"] == ""

    def test_khong_ghep_khi_phan_sau_da_co_role(self):
        els = merge_standalone_labels([
            text("el_1", "", parent="h", label="Relations:"),
            text("el_2", "ghi chú", parent="h", role="business_rule"),
        ])
        assert len(els) == 2


class TestLink:
    IR = {
        "schema_version": "1.0",
        "doc_id": "d1",
        "title": "T",
        "elements": [
            heading("el_1", "Table USERS"),
            text("el_2", "", parent="el_1", label="Columns:", role="column_intro"),
            table("el_3", parent="el_1"),
        ],
    }

    def test_gan_cay_tren_ban_sao(self):
        out = link(self.IR)
        assert "table" not in self.IR["elements"][1]     # input không bị sửa
        assert out["elements"][1]["table"] == "Table USERS"
        assert out["doc_id"] == "d1"

    def test_khong_con_truong_relations(self):
        """Quan hệ nghiệp vụ là việc của chặng `graph`, không phải chặng này."""
        assert "relations" not in link(self.IR)

    def test_tai_lieu_khong_heading_van_di_qua(self):
        """Không dựng được cây thì vẫn ra artifact, kèm cảnh báo - không ném lỗi."""
        ir = {**self.IR, "elements": [text("el_1", "chỉ có văn bản")]}
        out = link(ir)
        assert out["elements"][0]["parent_id"] is None
        assert out["elements"][0]["text"] == "chỉ có văn bản"
        assert any("nằm ngoài mọi heading" in w for w in out["warnings"])

    def test_canh_bao_phan_tu_ngoai_moi_heading(self):
        ir = {**self.IR, "elements": [
            text("el_1", "lời mở đầu"),
            heading("el_2", "Table USERS"),
            text("el_3", "body"),
        ]}
        assert any("nằm ngoài mọi heading" in w for w in check(link(ir)))

    def test_nhan_rong_co_bang_cung_cha_thi_khong_canh_bao(self):
        """Bản pdf xếp text xen giữa nhãn và bảng - xét theo cùng cha, không theo kề."""
        ir = {**self.IR, "elements": [
            heading("el_1", "Table USERS"),
            text("el_2", "", parent="el_1", label="Columns:", role="column_intro"),
            text("el_3", "chen giua", parent="el_1", role="business_rule"),
            table("el_4", parent="el_1"),
        ]}
        assert check(link(ir)) == []

    def test_nhan_rong_khong_co_object_nao_cung_cha(self):
        ir = {**self.IR, "elements": [
            heading("el_1", "Table USERS"),
            text("el_2", "", parent="el_1", label="Columns:", role="column_intro"),
        ]}
        assert any("không tìm được nội dung" in w for w in check(link(ir)))

    def test_heading_sau_nhat_khong_co_bang(self):
        ir = {**self.IR, "elements": [
            heading("el_1", "Table USERS"),
            table("el_2", parent="el_1"),
            heading("el_3", "Table ORDERS"),
            text("el_4", "quên mất bảng", parent="el_3"),
        ]}
        assert any("không có bảng nào bên dưới" in w for w in check(link(ir)))

    def test_tai_lieu_khong_co_bang_thi_bo_qua_luat_bang(self):
        ir = {**self.IR, "elements": [
            heading("el_1", "Chapter 1"),
            text("el_2", "toàn văn xuôi", parent="el_1"),
        ]}
        assert check(link(ir)) == []

    def test_envelope_rong(self):
        assert check({"elements": []}) == ["0 phần tử - extract không tạo được element nào"]

    def test_giu_warnings_cua_chang_truoc(self):
        ir = {**self.IR, "warnings": ["cảnh báo từ parse"]}
        assert link(ir)["warnings"][0] == "cảnh báo từ parse"

"""Kiểm chứng chỉ số bằng ví dụ tính tay.

Chỉ số sai thì mọi kết luận rút ra sau đó đều sai mà không có gì báo động. Đây là
chỗ chặn việc đó, chạy không cần Qdrant.
"""

from __future__ import annotations

import pytest

from src.branch_sql.eval import metrics as M
from src.branch_sql.eval.normalize import table_key

GOLD = {"point_of_sale", "v_bds_new_sub_sale_point", "v_user_precinct_permission"}
RANKED = ["point_of_sale", "precinct", "v_bds_new_sub_sale_point", "v_bds_site", "v_user_precinct_permission"]


class TestRecall:
    def test_partial(self):
        # top-3 chứa 2/3 bảng gold
        assert M.recall_at_k(GOLD, RANKED, 3) == pytest.approx(2 / 3)

    def test_full(self):
        assert M.recall_at_k(GOLD, RANKED, 5) == 1.0

    def test_k_lon_hon_ket_qua(self):
        assert M.recall_at_k(GOLD, RANKED, 99) == 1.0

    def test_gold_rong(self):
        assert M.recall_at_k(set(), RANKED, 3) == 1.0


class TestCeiling:
    def test_can_6_bang_lay_1_cho(self):
        assert M.ceiling_at_k(6, 1) == pytest.approx(1 / 6)

    def test_du_cho(self):
        assert M.ceiling_at_k(3, 5) == 1.0

    def test_normalized_dat_toi_da(self):
        # top-1 lấy được 1/3 bảng, mà trần của k=1 cũng là 1/3 -> đã tối ưu
        assert M.normalized_recall_at_k(GOLD, RANKED, 1) == pytest.approx(1.0)


class TestComplete:
    def test_thieu_mot_bang_la_false(self):
        assert M.complete_at_k(GOLD, RANKED, 4) is False

    def test_du_la_true(self):
        assert M.complete_at_k(GOLD, RANKED, 5) is True

    def test_khac_recall(self):
        """Recall cao vẫn có thể Complete = False. Đây là lý do phải báo cả hai."""
        assert M.recall_at_k(GOLD, RANKED, 4) == pytest.approx(2 / 3)
        assert M.complete_at_k(GOLD, RANKED, 4) is False


class TestPrecisionRank:
    def test_precision(self):
        assert M.precision_at_k(GOLD, RANKED, 4) == pytest.approx(2 / 4)

    def test_mean_rank(self):
        # gold nằm ở hạng 1, 3, 5
        assert M.mean_rank(GOLD, RANKED) == pytest.approx(3.0)

    def test_mean_rank_khong_tim_thay(self):
        assert M.mean_rank({"khong_ton_tai"}, RANKED) is None


class TestSample:
    def test_hit(self):
        assert M.hit_at_k({"SQL_001"}, ["SQL_009", "SQL_001"], 2) is True
        assert M.hit_at_k({"SQL_001"}, ["SQL_009", "SQL_001"], 1) is False

    def test_mrr(self):
        assert M.reciprocal_rank({"SQL_001"}, ["SQL_009", "SQL_001"]) == pytest.approx(0.5)
        assert M.reciprocal_rank({"SQL_001"}, ["SQL_009"]) == 0.0

    def test_jaccard(self):
        assert M.jaccard({"a", "b"}, {"b", "c"}) == pytest.approx(1 / 3)
        assert M.jaccard({"a"}, {"a"}) == 1.0
        assert M.jaccard(set(), set()) == 0.0

    def test_mean_jaccard(self):
        # {a,b} vs {a,b} = 1.0 ; {a,b} vs {c} = 0.0 -> trung binh 0.5
        assert M.mean_jaccard_at_k({"a", "b"}, [{"a", "b"}, {"c"}], 2) == pytest.approx(0.5)


class TestAggregate:
    def test_micro_khac_macro(self):
        """Case nhiều bảng phải có trọng số lớn hơn trong micro."""
        per_case = [
            {"n_found": 1, "n_gold": 1, "recall": 1.0},   # dễ, đúng hết
            {"n_found": 3, "n_gold": 6, "recall": 0.5},   # khó, đúng nửa
        ]
        assert M.micro_recall(per_case) == pytest.approx(4 / 7)
        assert M.summarize(per_case, ["recall"])["recall"] == pytest.approx(0.75)

    def test_summarize_bo_qua_none(self):
        per_case = [{"x": 1.0}, {"x": None}, {"x": 0.0}]
        assert M.summarize(per_case, ["x"])["x"] == pytest.approx(0.5)


class TestTableKey:
    """Chuẩn hoá phải gộp được hai cách viết của cùng một table function."""

    def test_dang_day_du_va_rut_gon_trung_nhau(self):
        full = "TABLE(pck_report_chatbox.get_rev_data_by_precinct (TO_DATE(TO_CHAR(:date), 'dd/mm/yyyy'), UPPER(:user_name)))"
        short = "TABLE(pck_report_chatbox.get_rev_data_by_precinct)"
        assert table_key(full) == table_key(short) == "get_rev_data_by_precinct"

    def test_ten_thuong(self):
        assert table_key("POINT_OF_SALE") == "point_of_sale"
        assert table_key(" V_BDS_SITE ") == "v_bds_site"

    def test_rong(self):
        assert table_key(None) == ""
        assert table_key("") == ""

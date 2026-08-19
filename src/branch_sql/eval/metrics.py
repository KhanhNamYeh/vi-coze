"""Định nghĩa chỉ số. Hàm thuần, không đọc file, không gọi Qdrant.

Tách khỏi `retrieval_eval.py` để kiểm chứng được bằng ví dụ tính tay, không cần
dựng hạ tầng. Mọi tranh cãi "chỉ số này tính đúng chưa" xử ở đây.

Gold của bộ đo là một TẬP bảng, không phải danh sách xếp hạng. Nên chỉ số phải
là chỉ số trên tập; dùng thẳng nDCG cho trường hợp này là sai công cụ.
"""

from __future__ import annotations

from statistics import mean


# ---- chỉ số trên tập (dùng cho chunk docs) --------------------------------

def recall_at_k(gold: set[str], ranked: list[str], k: int) -> float:
    """Bao nhiêu phần trăm bảng gold nằm trong top-k."""
    if not gold:
        return 1.0
    return len(gold & set(ranked[:k])) / len(gold)


def ceiling_at_k(n_gold: int, k: int) -> float:
    """Recall cao nhất có thể đạt với k chỗ.

    Case cần 6 bảng thì recall@1 tối đa là 1/6. Không có trần này thì con số
    recall@1 thấp bị đọc nhầm thành truy hồi kém.
    """
    if n_gold <= 0:
        return 1.0
    return min(1.0, k / n_gold)


def normalized_recall_at_k(gold: set[str], ranked: list[str], k: int) -> float:
    """recall@k chia cho trần của chính nó. 1.0 = đã lấy hết mức k cho phép."""
    ceil = ceiling_at_k(len(gold), k)
    return recall_at_k(gold, ranked, k) / ceil if ceil else 1.0


def complete_at_k(gold: set[str], ranked: list[str], k: int) -> bool:
    """Top-k có chứa ĐỦ bảng gold không.

    Đây là chỉ số quyết định với Text-to-SQL: thiếu một bảng là JOIN gãy, câu SQL
    sai hoàn toàn. Recall 80% nghe ổn nhưng có thể ứng với Complete 30%.
    """
    return gold <= set(ranked[:k])


def precision_at_k(gold: set[str], ranked: list[str], k: int) -> float:
    """Tỷ lệ chỗ trong top-k thực sự là bảng gold."""
    top = ranked[:k]
    return len(gold & set(top)) / len(top) if top else 0.0


# ---- chỉ số theo thứ hạng (dùng cho chunk sample) -------------------------

def hit_at_k(relevant: set[str], ranked: list[str], k: int) -> bool:
    """Top-k có ít nhất một mục liên quan không.

    Với ví dụ few-shot thì đủ dùng: prompt chỉ cần vài ví dụ tốt, không cần lấy
    hết mọi ví dụ liên quan.
    """
    return bool(relevant & set(ranked[:k]))


def reciprocal_rank(relevant: set[str], ranked: list[str]) -> float:
    """1/hạng của mục liên quan đầu tiên. 0 nếu không có mục nào."""
    for i, r in enumerate(ranked, 1):
        if r in relevant:
            return 1.0 / i
    return 0.0


def mean_rank(gold: set[str], ranked: list[str]) -> float | None:
    """Hạng trung bình của các mục gold tìm được. None nếu không tìm được mục nào."""
    ranks = [i for i, r in enumerate(ranked, 1) if r in gold]
    return mean(ranks) if ranks else None


# ---- độ giống theo tập bảng (định nghĩa "ví dụ liên quan") -----------------

def jaccard(a: set[str], b: set[str]) -> float:
    """|giao| / |hợp|. 0 khi cả hai rỗng."""
    if not a and not b:
        return 0.0
    return len(a & b) / len(a | b)


def mean_jaccard_at_k(gold: set[str], ranked_tables: list[set[str]], k: int) -> float:
    """Độ giống trung bình của k ví dụ đầu với tập bảng của câu hỏi.

    Chỉ số liên tục, không cần chọn ngưỡng - tránh việc đổi ngưỡng làm đổi kết
    luận. Dùng kèm `hit_at_k` chứ không thay nó.
    """
    top = ranked_tables[:k]
    return mean(jaccard(gold, t) for t in top) if top else 0.0


# ---- cộng dồn nhiều case --------------------------------------------------

def summarize(per_case: list[dict], keys: list[str]) -> dict:
    """Trung bình theo case (macro) cho các khoá số / bool đã cho."""
    out = {}
    for key in keys:
        vals = [c[key] for c in per_case if c.get(key) is not None]
        out[key] = mean(float(v) for v in vals) if vals else None
    return out


def micro_recall(per_case: list[dict]) -> float:
    """Tổng bảng tìm được / tổng bảng gold, gộp mọi case.

    Khác macro: case nhiều bảng có trọng số lớn hơn. Báo cáo cả hai, vì bộ đo có
    case 1 bảng lẫn case 6 bảng.
    """
    found = sum(c["n_found"] for c in per_case)
    total = sum(c["n_gold"] for c in per_case)
    return found / total if total else 1.0

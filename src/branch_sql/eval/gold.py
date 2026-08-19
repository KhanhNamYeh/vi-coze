"""Nạp các tập đo, dựng gold cho cả hai loại chunk.

    uv run python -m src.branch_sql.eval.gold

Ba tập, ba vai trò:

    dev.json              18 câu hỏi để chỉnh tham số
    test.json             15 câu hỏi để báo cáo cuối
    fewshot.chunks.json   18 ví dụ đem đi index - CÙNG 18 dòng với dev

Chỗ dễ sai nhất nằm ở dòng cuối: `dev` và `fewshot` là cùng một dữ liệu ở hai vai
trò. Đo `dev` trên chỉ mục có chứa `fewshot` thì mỗi câu hỏi sẽ tìm thấy chính
nó, giống nhau tuyệt đối, và nội dung của nó tự khai đáp án. Số đo lúc đó là số
đo trí nhớ. `assert_no_leak` chặn đúng tình huống này.

Chunk docs có gold sẵn: `relevant_chunks` là tên bảng, một bảng là một chunk.

Chunk fewshot thì KHÔNG có gold do người gán. Ở đây suy ra bằng độ trùng tập bảng
giữa ví dụ và câu hỏi. Đây là chỉ báo thay thế, không phải nhãn người gán - một
ví dụ dùng cùng bộ bảng thì gần như chắc chắn minh hoạ cùng kiểu JOIN, nhưng
không có gì bảo đảm nó là ví dụ tốt nhất. Kết luận rút ra phải nói rõ điều này.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

from ..config import EVAL_DIR, PROCESSED_DIR, rel
from .metrics import jaccard
from .normalize import table_key

DEV_PATH = EVAL_DIR / "dev.json"
TEST_PATH = EVAL_DIR / "test.json"
FEWSHOT_PATH = PROCESSED_DIR / "fewshot.chunks.json"

# Có mặt ở gần như mọi case vì là luật quyền truy cập, không phải vì câu hỏi nói
# tới nó. Để nguyên thì mọi cặp câu hỏi - ví dụ đều được cộng điểm giống nhau.
PERMISSION_TABLE = "v_user_precinct_permission"

# Ngưỡng coi một ví dụ là liên quan, sau khi đã bỏ bảng quyền.
RELEVANT_JACCARD = 0.5


@dataclass(frozen=True)
class Case:
    """Một câu hỏi trong tập đo (dev hoặc test)."""

    id: str
    query: str
    gold_tables: set[str]                                # table_key, gồm cả bảng quyền
    core_tables: set[str] = field(default_factory=set)   # đã bỏ bảng quyền

    @property
    def n_gold(self) -> int:
        return len(self.gold_tables)

    @property
    def requires_permission(self) -> bool:
        return PERMISSION_TABLE in self.gold_tables


@dataclass(frozen=True)
class FewShot:
    """Một ví dụ trong bộ tri thức đem đi index."""

    id: str
    query: str
    tables: set[str]
    core_tables: set[str] = field(default_factory=set)


def _keys(names: list[str]) -> set[str]:
    return {table_key(n) for n in names if n}


def _load(path: Path) -> list[dict]:
    if not path.exists():
        raise FileNotFoundError(
            f"không thấy {rel(path)} - chạy "
            "`uv run --extra eval python -m src.branch_sql.eval.gold_parse` trước"
        )
    return json.loads(path.read_text(encoding="utf-8"))


def load_cases(path: Path) -> list[Case]:
    out = []
    for r in _load(path):
        tables = _keys(r["relevant_chunks"])
        out.append(
            Case(
                id=r["test_case_id"],
                query=r["query"],
                gold_tables=tables,
                core_tables=tables - {PERMISSION_TABLE},
            )
        )
    return out


def load_dev() -> list[Case]:
    return load_cases(DEV_PATH)


def load_test() -> list[Case]:
    return load_cases(TEST_PATH)


def load_split(split: str) -> list[Case]:
    return {"dev": load_dev, "test": load_test}[split]()


def load_fewshot(path: Path = FEWSHOT_PATH) -> list[FewShot]:
    out = []
    for r in _load(path):
        tables = _keys(r["relevant_chunks"])
        out.append(
            FewShot(
                id=r["test_case_id"],
                query=r["query"],
                tables=tables,
                core_tables=tables - {PERMISSION_TABLE},
            )
        )
    return out


def fewshot_similarity(case: Case, shots: list[FewShot], *, drop_permission: bool = True) -> dict[str, float]:
    """fewshot_id -> jaccard với tập bảng của case."""
    a = case.core_tables if drop_permission else case.gold_tables
    return {s.id: jaccard(a, s.core_tables if drop_permission else s.tables) for s in shots}


def relevant_fewshots(
    case: Case,
    shots: list[FewShot],
    *,
    threshold: float = RELEVANT_JACCARD,
    drop_permission: bool = True,
) -> set[str]:
    """Tập fewshot_id được coi là liên quan với case."""
    sim = fewshot_similarity(case, shots, drop_permission=drop_permission)
    return {sid for sid, v in sim.items() if v >= threshold}


def assert_no_leak(cases: list[Case], shots: list[FewShot], *, split: str) -> None:
    """Tập đo không được trùng id với bộ fewshot đang nằm trong chỉ mục."""
    shared = {c.id for c in cases} & {s.id for s in shots}
    if shared:
        raise ValueError(
            f"rò rỉ: {len(shared)}/{len(cases)} câu hỏi của tập '{split}' cũng nằm trong "
            f"bộ fewshot đã index ({sorted(shared)[:3]}...).\n"
            f"'dev' và 'fewshot' là cùng 18 dòng - chỉ đo 'dev' trên setup 'docs', "
            f"hoặc đo 'fewshot'/'both' bằng tập 'test'."
        )


def main(argv: list[str]) -> int:
    try:
        dev, test, shots = load_dev(), load_test(), load_fewshot()
    except (FileNotFoundError, ValueError) as e:
        print(e, file=sys.stderr)
        return 1

    for name, cases in (("dev ", dev), ("test", test)):
        sizes = sorted(c.n_gold for c in cases)
        n_perm = sum(1 for c in cases if c.requires_permission)
        print(f"{name} : {len(cases):>2} case ({cases[0].id}..{cases[-1].id})"
              f" | bảng/case min={sizes[0]} p50={sizes[len(sizes) // 2]} max={sizes[-1]}"
              f" | cần bảng quyền {n_perm}/{len(cases)}")
    print(f"fewshot: {len(shots):>2} ví dụ ({shots[0].id}..{shots[-1].id}) - đem đi index\n")

    overlap = {c.id for c in dev} & {s.id for s in shots}
    print(f"dev  ∩ fewshot = {len(overlap)}/{len(dev)}  -> dev chỉ đo được setup 'docs'")
    print(f"test ∩ fewshot = {len({c.id for c in test} & {s.id for s in shots})}/{len(test)}"
          f"  -> test đo được cả ba setup\n")

    kmax = max(c.n_gold for c in test)
    print(f"k phải >= {kmax} thì Complete@k trên test mới có thể đạt 1.0")
    print(f"mỗi case chiếm {100 / len(test):.1f}% điểm -> chênh dưới ~{100 / len(test):.0f} điểm là nhiễu\n")

    print(f"ví dụ liên quan mỗi case của test (jaccard >= {RELEVANT_JACCARD}, đã bỏ bảng quyền):")
    empty = []
    for c in test:
        rel_ids = relevant_fewshots(c, shots)
        if not rel_ids:
            empty.append(c.id)
        best = max(fewshot_similarity(c, shots).items(), key=lambda kv: kv[1])
        print(f"  {c.id}  {len(rel_ids):>2} ví dụ | giống nhất {best[0]} ({best[1]:.2f})")

    if empty:
        print(f"\n! {len(empty)} case không có ví dụ nào đạt ngưỡng: {', '.join(empty)}")
        print("  các case này không đo được ở setup 'fewshot' - phải báo cáo riêng")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

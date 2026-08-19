"""Chạy truy hồi trên tập đo rồi cộng dồn chỉ số.

    docker compose up -d
    uv run python -m src.branch_sql.eval.retrieval_eval --split dev --setup docs
    uv run python -m src.branch_sql.eval.retrieval_eval --split test

Ba cấu hình nguồn (`--setup`) nhân ba chế độ truy hồi (`--mode`):

    docs     chỉ chunk schema  | dense   chỉ vector dày
    fewshot  chỉ chunk ví dụ   | sparse  chỉ BM25
    both     trộn cả hai       | hybrid  RRF cả hai

Tập nào đo được setup nào:

    dev  + docs             chỉnh chunking, chỉnh k, chỉnh mode - lặp thoải mái
    dev  + fewshot/both     BỊ CHẶN: dev và fewshot là cùng 18 dòng, mỗi câu hỏi
                            sẽ tìm thấy chính nó -> đo trí nhớ, không phải đo hệ thống
    test + tất cả           báo cáo cuối

Cấu hình `both` dùng CHUNG một ngân sách k cho cả hai loại, nên nó trả lời đúng
một câu hỏi: ví dụ có chiếm mất chỗ của bảng không. So `Complete@k` của `both`
với của `docs` là ra chi phí chen chỗ. Nếu chi phí đó lớn thì kết luận là đừng
trộn chung một pool - cấp ngân sách riêng cho mỗi loại rồi ghép kết quả.
"""

from __future__ import annotations

import argparse
import sys

from ..config import COLLECTION
from . import gold as G
from . import metrics as M
from .normalize import table_key

K_SWEEP = (1, 3, 5, 10, 20)

# Điểm fewshot phải mang hai trường này thì runner mới phân loại được.
KIND_FIELD = "kind"
FEWSHOT_KIND = "fewshot"
FEWSHOT_ID_FIELD = "test_case_id"


def fewshot_collection() -> str:
    """Collection của chunk ví dụ. Tách khỏi collection schema."""
    return f"{COLLECTION}__fewshot"


def identify(payload: dict) -> tuple[str, str]:
    """payload của một điểm -> (loại, định danh dùng để đối chiếu gold)."""
    if payload.get(KIND_FIELD) == FEWSHOT_KIND or FEWSHOT_ID_FIELD in payload:
        return "fewshot", payload.get(FEWSHOT_ID_FIELD, "")
    return "docs", table_key(payload.get("table_name"))


def retrieve(query: str, *, k: int, mode: str, setup: str) -> list[tuple[str, str]]:
    """Trả [(loại, định danh)] đã xếp hạng giảm dần."""
    from ..online.qdrant_retriever import search

    collections = {
        "docs": [COLLECTION],
        "fewshot": [fewshot_collection()],
        "both": [COLLECTION, fewshot_collection()],
    }[setup]

    hits: list[tuple[float, str, str]] = []
    for coll in collections:
        for score, doc in search(query, k=k, mode=mode, collection=coll):
            kind, ident = identify(doc.metadata)
            if ident:
                hits.append((score, kind, ident))

    # Điểm giữa hai collection không cùng thang đo tuyệt đối, nhưng cùng mode và
    # cùng model nên xếp chung được. Đây chính là điều `both` cần mô phỏng.
    hits.sort(key=lambda h: -h[0])
    return [(kind, ident) for _, kind, ident in hits[:k]]


def eval_case(case: G.Case, shots: list[G.FewShot], ranked: list[tuple[str, str]], k: int) -> dict:
    """Chỉ số của một case ở một mức k."""
    docs_ranked = [i for kind, i in ranked if kind == "docs"]
    shot_ranked = [i for kind, i in ranked if kind == "fewshot"]

    sim = G.fewshot_similarity(case, shots)
    relevant = G.relevant_fewshots(case, shots)
    by_id = {s.id: s for s in shots}

    return {
        "id": case.id,
        "k": k,
        "n_gold": case.n_gold,
        "n_found": len(case.gold_tables & set(docs_ranked[:k])),
        "requires_permission": case.requires_permission,
        "permission_found": (
            G.PERMISSION_TABLE in docs_ranked[:k] if case.requires_permission else None
        ),
        # --- chunk docs: chỉ số trên tập
        "recall": M.recall_at_k(case.gold_tables, docs_ranked, k),
        "recall_core": M.recall_at_k(case.core_tables, docs_ranked, k),
        "recall_norm": M.normalized_recall_at_k(case.gold_tables, docs_ranked, k),
        "complete": M.complete_at_k(case.gold_tables, docs_ranked, k),
        "complete_core": M.complete_at_k(case.core_tables, docs_ranked, k),
        "precision": M.precision_at_k(case.gold_tables, docs_ranked, k),
        "mean_rank": M.mean_rank(case.gold_tables, docs_ranked),
        # --- chunk fewshot: chỉ số theo thứ hạng
        "fewshot_hit": M.hit_at_k(relevant, shot_ranked, k),
        "fewshot_mrr": M.reciprocal_rank(relevant, shot_ranked),
        "fewshot_jaccard": M.mean_jaccard_at_k(
            case.core_tables,
            [by_id[i].core_tables for i in shot_ranked if i in by_id],
            k,
        ),
        "fewshot_best_sim": max(sim.values()) if sim else 0.0,
        # --- thành phần top-k
        "n_docs_in_topk": len(docs_ranked[:k]),
        "n_fewshot_in_topk": len(shot_ranked[:k]),
    }


AGG_KEYS = [
    "recall", "recall_core", "recall_norm", "complete", "complete_core",
    "precision", "fewshot_hit", "fewshot_mrr", "fewshot_jaccard",
    "n_docs_in_topk", "n_fewshot_in_topk",
]


def run(split: str, setup: str, mode: str, *, ks: tuple[int, ...] = K_SWEEP) -> dict[int, dict]:
    cases = G.load_split(split)
    shots = G.load_fewshot()

    # Chỉ mục chỉ chứa fewshot ở setup 'fewshot' và 'both'. Setup 'docs' không
    # đụng tới nó nên dev dùng được.
    if setup in ("fewshot", "both"):
        G.assert_no_leak(cases, shots, split=split)

    out = {}
    for k in ks:
        per_case = [
            eval_case(c, shots, retrieve(c.query, k=k, mode=mode, setup=setup), k)
            for c in cases
        ]
        agg = M.summarize(per_case, AGG_KEYS)
        agg["micro_recall"] = M.micro_recall(per_case)

        perm = [c for c in per_case if c["requires_permission"]]
        agg["permission_recall"] = (
            sum(1 for c in perm if c["permission_found"]) / len(perm) if perm else None
        )
        agg["_per_case"] = per_case
        out[k] = agg
    return out


def print_table(split: str, setup: str, mode: str, res: dict[int, dict]) -> None:
    docs = setup in ("docs", "both")
    shot = setup in ("fewshot", "both")

    print(f"\n=== split={split}  setup={setup}  mode={mode} ===")
    head = ["k"]
    if docs:
        head += ["Recall", "R-core", "R-norm", "Complete", "C-core", "micro", "Perm"]
    if shot:
        head += ["Hit", "MRR", "Jaccard"]
    if setup == "both":
        head += ["#docs", "#shot"]
    print("  " + "".join(f"{h:>10}" for h in head))

    for k, a in res.items():
        row = [f"{k:>10}"]
        if docs:
            row += [
                f"{a['recall']:>10.3f}", f"{a['recall_core']:>10.3f}",
                f"{a['recall_norm']:>10.3f}", f"{a['complete']:>10.3f}",
                f"{a['complete_core']:>10.3f}", f"{a['micro_recall']:>10.3f}",
                f"{a['permission_recall']:>10.3f}" if a["permission_recall"] is not None else f"{'-':>10}",
            ]
        if shot:
            row += [
                f"{a['fewshot_hit']:>10.3f}", f"{a['fewshot_mrr']:>10.3f}",
                f"{a['fewshot_jaccard']:>10.3f}",
            ]
        if setup == "both":
            row += [f"{a['n_docs_in_topk']:>10.1f}", f"{a['n_fewshot_in_topk']:>10.1f}"]
        print("  " + "".join(row))


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(prog="retrieval_eval")
    p.add_argument("--split", choices=["dev", "test"], default="test")
    p.add_argument("--setup", choices=["docs", "fewshot", "both", "all"], default="all")
    p.add_argument("--mode", choices=["dense", "sparse", "hybrid", "all"], default="all")
    args = p.parse_args(argv)

    setups = ["docs", "fewshot", "both"] if args.setup == "all" else [args.setup]
    modes = ["dense", "sparse", "hybrid"] if args.mode == "all" else [args.mode]

    if args.split == "dev" and args.setup == "all":
        setups = ["docs"]
        print("split=dev nên chỉ chạy setup 'docs' - xem docstring")

    for setup in setups:
        for mode in modes:
            try:
                res = run(args.split, setup, mode)
            except (FileNotFoundError, ValueError) as e:
                print(e, file=sys.stderr)
                return 1
            except Exception as e:  # noqa: BLE001
                print(f"lỗi (setup={setup}, mode={mode}): {e}", file=sys.stderr)
                print("Qdrant đã chạy chưa?  docker compose up -d", file=sys.stderr)
                print("chunk fewshot đã index chưa?", file=sys.stderr)
                return 1
            print_table(args.split, setup, mode, res)

    print("\nComplete@k là chỉ số quyết định: thiếu một bảng là JOIN gãy.")
    print("R-core / C-core đã bỏ bảng quyền - so với cột thường để thấy phần thiếu hụt")
    print("do luật quyền truy cập, thứ mà truy hồi theo ngữ nghĩa không lấy được.")
    if args.split == "test":
        print("Số trên test là số báo cáo - đừng chỉnh tham số dựa trên nó.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

"""Đo và chỉnh tham số truy hồi trên tập dev. Chặng `verify`.

    uv run python -m src.branch_sql.offline.verify.retrieval
    uv run python -m src.branch_sql.offline.verify.retrieval --doc mo_ta_bang_bds_new__pdf

Tập `data/eval/sql/dev.json` có 18 câu hỏi, mỗi câu kèm `relevant_chunks` là tên
các bảng phải tìm ra. Một bảng là một chunk, nên tên bảng đúng là nhãn cần đo.

DEV DÙNG ĐỂ CHỈNH THAM SỐ, KHÔNG DÙNG ĐỂ BÁO CÁO. Chọn cấu hình tốt nhất trên
chính tập đã dùng để chọn thì con số đó là tối ưu hoá trên nhiễu, không phải
chất lượng thật. Chốt xong tham số bằng dev thì chạy `test.json` một lần duy
nhất để lấy số đưa vào báo cáo.

Quét bốn trục:

    mode         dense | sparse | rrf | wrrf     đường truy hồi nào
    candidate_k  số ứng viên mỗi nhánh trước khi fuse
    rrf_k        hằng số mềm của RRF - nhỏ thì thiên vị top đầu   (chỉ wrrf)
    weights      trọng số dense/sparse                            (chỉ wrrf)

So sánh bằng `recall@k` vì bài toán là "tìm đủ bảng để viết được câu SQL": thiếu
một bảng là câu SQL sai, còn thừa một bảng thì LLM bỏ qua được. `complete@k` -
tỷ lệ câu tìm ĐỦ mọi bảng - là chỉ số sát nhất với thành/bại thực tế.
"""

from __future__ import annotations

import argparse
import json
import sys

from ...config import CANDIDATE_K, CFG, EVAL_DIR, RRF_K, rel
from ...eval import metrics as M
from ...eval.normalize import table_key
from ...online.qdrant_retriever import search

K_REPORT = 5
SWEEP_CANDIDATE = (10, 20, 50)
SWEEP_RRF_K = (10, 40, 60)
SWEEP_WEIGHTS = ((0.5, 0.5), (0.7, 0.3), (0.3, 0.7))


def load_dev(path=None) -> list[dict]:
    src = path or EVAL_DIR / "dev.json"
    if not src.exists():
        raise FileNotFoundError(f"không thấy tập dev tại {rel(src)}")
    cases = json.loads(src.read_text(encoding="utf-8"))
    if not cases:
        raise ValueError(f"{rel(src)}: rỗng")
    return cases


def docs_collection(project: int | None = None) -> str:
    """Collection TÀI LIỆU của một dự án. Không dùng hằng `index.collection`:
    nguồn sự thật là `knowledge[].collection`, hằng kia chỉ là mặc định."""
    project = project if project is not None else CFG.project
    if project is None:
        raise ValueError("chưa biết dự án - đặt VI_COZE_PROJECT hoặc truyền --project")
    for k in CFG.knowledge_of(project):
        name = k.collection_for(project)
        if not name.endswith("__sql"):
            return name
    raise ValueError(f"dự án {project} không có bộ tri thức tài liệu nào")


def ranked_tables(query: str, *, k: int, doc_id: str | None, **kw) -> list[str]:
    """Kết quả truy hồi -> danh sách tên bảng đã chuẩn hoá, giữ thứ hạng, bỏ trùng.

    Bỏ trùng vì cùng một bảng có thể ra từ nhiều chunk (bản DOCX và bản PDF của
    cùng tài liệu). Đếm nó hai lần là tự thổi phồng precision.
    """
    kw.setdefault("collection", docs_collection())
    hits = search(query, k=k, doc_id=doc_id, **kw)
    out: list[str] = []
    for _, doc in hits:
        key = table_key(doc.metadata.get("table_name"))
        if key and key not in out:
            out.append(key)
    return out


def evaluate(cases: list[dict], *, k: int = K_REPORT, doc_id: str | None = None,
             **kw) -> dict:
    """Chạy hết tập dev với một bộ tham số -> số đo tổng hợp."""
    per_case = []
    for case in cases:
        gold = {table_key(t) for t in case["relevant_chunks"]}
        ranked = ranked_tables(case["query"], k=k, doc_id=doc_id, **kw)
        per_case.append({
            "id": case["test_case_id"],
            "recall": M.recall_at_k(gold, ranked, k),
            "complete": float(M.complete_at_k(gold, ranked, k)),
            "precision": M.precision_at_k(gold, ranked, k),
            "mrr": M.reciprocal_rank(gold, ranked),
            "n_gold": len(gold),
            "n_found": len(gold & set(ranked[:k])),
        })
    out = M.summarize(per_case, ["recall", "complete", "precision", "mrr"])
    out["micro_recall"] = M.micro_recall(per_case)
    out["per_case"] = per_case
    return out


def sweep(cases: list[dict], *, k: int = K_REPORT, doc_id: str | None = None) -> list[dict]:
    """Quét không gian tham số. Trả danh sách đã sắp theo recall giảm dần."""
    runs: list[dict] = []

    for mode in ("dense", "sparse"):
        res = evaluate(cases, k=k, doc_id=doc_id, mode=mode)
        runs.append({"mode": mode, "candidate_k": "-", "rrf_k": "-", "w": "-", **res})

    for candidate_k in SWEEP_CANDIDATE:
        res = evaluate(cases, k=k, doc_id=doc_id, mode="rrf", candidate_k=candidate_k)
        runs.append({"mode": "rrf", "candidate_k": candidate_k, "rrf_k": "server",
                     "w": "-", **res})

    for candidate_k in SWEEP_CANDIDATE:
        for rrf_k in SWEEP_RRF_K:
            for w in SWEEP_WEIGHTS:
                res = evaluate(cases, k=k, doc_id=doc_id, mode="wrrf",
                               candidate_k=candidate_k, rrf_k=rrf_k, weights=w)
                runs.append({"mode": "wrrf", "candidate_k": candidate_k, "rrf_k": rrf_k,
                             "w": f"{w[0]:.1f}/{w[1]:.1f}", **res})

    # Sắp theo complete trước: tìm ĐỦ bảng mới viết được SQL, recall là phụ.
    runs.sort(key=lambda r: (r["complete"], r["recall"], r["mrr"]), reverse=True)
    return runs


def print_sweep(runs: list[dict], k: int) -> None:
    print(f"\n{'mode':<7}{'cand':>5}{'rrf_k':>7}{'w d/s':>8} | "
          f"{'complete':>9}{'recall':>8}{'micro':>7}{'prec':>7}{'mrr':>7}   (k={k})")
    print("-" * 78)
    for r in runs:
        print(f"{r['mode']:<7}{str(r['candidate_k']):>5}{str(r['rrf_k']):>7}{str(r['w']):>8} | "
              f"{r['complete']:>9.3f}{r['recall']:>8.3f}{r['micro_recall']:>7.3f}"
              f"{r['precision']:>7.3f}{r['mrr']:>7.3f}")


def print_best(best: dict, cases: list[dict], k: int) -> None:
    print(f"\nTốt nhất: mode={best['mode']} candidate_k={best['candidate_k']} "
          f"rrf_k={best['rrf_k']} weights={best['w']}")
    print(f"  complete@{k}={best['complete']:.3f}  recall@{k}={best['recall']:.3f}  "
          f"mrr={best['mrr']:.3f}")

    miss = [c for c in best["per_case"] if c["complete"] < 1]
    if not miss:
        print(f"  mọi câu hỏi đều tìm đủ bảng trong top-{k}")
        return
    print(f"  {len(miss)}/{len(cases)} câu chưa tìm đủ bảng:")
    by_id = {c["test_case_id"]: c for c in cases}
    for c in miss[:5]:
        q = by_id[c["id"]]["query"][:52]
        print(f"    {c['id']}  {c['n_found']}/{c['n_gold']} bảng  \"{q}...\"")


def print_config(best: dict) -> None:
    """In khối JSON dán thẳng vào `retrieval` của profile."""
    mode = "hybrid" if best["mode"] in ("rrf", "wrrf") else best["mode"]
    print("\nDán vào config/sql.json:")
    print(f'  "retrieval": {{')
    print(f'    "mode": "{mode}",')
    print(f'    "candidate_k": {best["candidate_k"] if best["candidate_k"] != "-" else CANDIDATE_K},')
    print(f'    "rrf_k": {best["rrf_k"] if isinstance(best["rrf_k"], int) else RRF_K},')
    if best["w"] != "-":
        a, b = best["w"].split("/")
        print(f'    "rrf_weights": [{a}, {b}],')
    print('    "rerank": { "model": "AITeamVN/Vietnamese_Reranker", "top_n": 5 }')
    print("  }")


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--doc", default=None,
                    help="chỉ đo trên một doc_id (mặc định: cả collection)")
    ap.add_argument("-k", type=int, default=K_REPORT, help=f"top-k (mặc định {K_REPORT})")
    ap.add_argument("--quick", action="store_true",
                    help="chỉ so bốn chế độ, bỏ quét tham số")
    args = ap.parse_args(argv)

    try:
        cases = load_dev()
    except (FileNotFoundError, ValueError) as e:
        print(e, file=sys.stderr)
        return 1

    print(f"dev: {len(cases)} câu hỏi | doc_id={args.doc or 'tất cả'} | top-{args.k}")

    try:
        if args.quick:
            runs = [
                {"mode": m, "candidate_k": CANDIDATE_K, "rrf_k": "-", "w": "-",
                 **evaluate(cases, k=args.k, doc_id=args.doc, mode=m)}
                for m in ("dense", "sparse", "rrf", "wrrf")
            ]
            runs.sort(key=lambda r: (r["complete"], r["recall"]), reverse=True)
        else:
            runs = sweep(cases, k=args.k, doc_id=args.doc)
    except Exception as e:  # noqa: BLE001
        print(f"lỗi truy hồi: {e}\n  Qdrant chạy chưa? `docker compose up -d`",
              file=sys.stderr)
        return 1

    print_sweep(runs, args.k)
    print_best(runs[0], cases, args.k)
    print_config(runs[0])
    print("\nDev chỉ để CHỌN tham số. Số đưa vào báo cáo phải đo trên test.json.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

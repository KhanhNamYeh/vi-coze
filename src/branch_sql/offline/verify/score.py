"""Chấm điểm truy hồi của MỘT dự án. Chặng `verify`.

    VI_COZE_PROJECT=1 uv run python -m src.branch_sql.offline.verify.score 1
    VI_COZE_PROJECT=1 uv run python -m src.branch_sql.offline.verify.score 1 --split test

Một câu hỏi được truy hồi trên HAI đường của dự án, mỗi đường một trần khác nhau:

    tài liệu     top-5   collection `..__docs`  -> tên bảng nằm ngay ở table_name
    SQL sample   top-3   collection `..__sql`   -> tên bảng suy từ mẫu khớp được

Điểm của một câu:

    (recall_docs@5 + recall_sql@3) / 2

Hai vế đều là "số bảng gold tìm được / tổng bảng gold". Chia đôi để điểm nằm
trong [0, 1]; báo cáo cả hai vế riêng vì chúng hỏng theo hai kiểu khác nhau -
vế tài liệu yếu là truy hồi kém, vế sample yếu là bộ mẫu chưa phủ dạng câu hỏi.

CHẶN RÒ RỈ: tập `dev.json` và bộ SQL sample đem đi index là CÙNG 18 dòng. Truy
hồi vế sample sẽ luôn tìm thấy chính câu hỏi đang hỏi, và mẫu đó tự khai đáp án.
Điểm lúc đó là điểm trí nhớ, không phải điểm truy hồi. Vì vậy mẫu trùng
`test_case_id` với câu hỏi bị loại khỏi kết quả trước khi chấm.
"""

from __future__ import annotations

import argparse
import json
import sys

from ...config import CFG, EVAL_DIR, collections_of, rel
from ...eval import metrics as M
from ...eval.normalize import table_key
from ...online.qdrant_retriever import search

K_DOCS = 5
K_SQL = 3


def load_split(split: str) -> list[dict]:
    src = EVAL_DIR / f"{split}.json"
    if not src.exists():
        raise FileNotFoundError(f"không thấy {rel(src)}")
    cases = json.loads(src.read_text(encoding="utf-8"))
    if not cases:
        raise ValueError(f"{rel(src)}: rỗng")
    return cases


def sample_tables(cases: list[dict]) -> dict[str, set[str]]:
    """`test_case_id -> tập bảng của mẫu đó`, dùng để chấm vế SQL sample."""
    return {c["test_case_id"]: {table_key(t) for t in c["relevant_chunks"]} for c in cases}


def docs_tables(query: str, collection: str, *, k: int = K_DOCS, **kw) -> list[str]:
    """Truy hồi tài liệu -> tên bảng theo thứ hạng, bỏ trùng."""
    out: list[str] = []
    for _, doc in search(query, k=k, collection=collection, **kw):
        key = table_key(doc.metadata.get("table_name"))
        if key and key not in out:
            out.append(key)
    return out


def sql_tables(query: str, collection: str, *, exclude: str, by_id: dict[str, set[str]],
               k: int = K_SQL, **kw) -> tuple[set[str], list[str]]:
    """Truy hồi SQL sample -> tập bảng gộp từ các mẫu khớp được.

    Lấy dư một mẫu rồi mới loại mẫu trùng câu hỏi, để sau khi loại vẫn còn đủ k.
    """
    found: set[str] = set()
    used: list[str] = []
    for _, doc in search(query, k=k + 1, collection=collection, **kw):
        sid = doc.metadata.get("table_name")
        if sid == exclude or sid not in by_id:
            continue
        used.append(sid)
        found |= by_id[sid]
        if len(used) >= k:
            break
    return found, used


def evaluate(cases: list[dict], project: int, *, indexed: list[dict] | None = None,
             **kw) -> dict:
    """Chấm một tập câu hỏi.

    `indexed` là các mẫu THẬT SỰ nằm trong collection SQL sample - luôn là bộ
    `dev`, vì đó là sheet duy nhất được dựng thành .md và đem đi index. Dùng
    chính `cases` để tra tên bảng là sai khi chấm tập test: mẫu tìm được mang mã
    SQL_001..033 còn `cases` là SQL_034..050, nên MỌI mẫu đều bị loại và vế
    sample ra 0 tuyệt đối - trông như truy hồi hỏng chứ không như lỗi đối chiếu.
    """
    docs_coll, sql_coll = collections_of(project)
    by_id = sample_tables(indexed if indexed is not None else cases)

    per_case = []
    for case in cases:
        gold = {table_key(t) for t in case["relevant_chunks"]}
        ranked = docs_tables(case["query"], docs_coll, **kw)
        hit_sql, used = sql_tables(case["query"], sql_coll,
                                   exclude=case["test_case_id"], by_id=by_id, **kw)

        r_docs = M.recall_at_k(gold, ranked, K_DOCS)
        r_sql = len(gold & hit_sql) / len(gold) if gold else 1.0
        per_case.append({
            "id": case["test_case_id"],
            "recall_docs": r_docs,
            "recall_sql": r_sql,
            "score": (r_docs + r_sql) / 2,
            "complete_docs": float(M.complete_at_k(gold, ranked, K_DOCS)),
            "n_gold": len(gold),
            "n_found": len(gold & set(ranked[:K_DOCS])),
            "samples": used,
        })

    out = M.summarize(per_case, ["recall_docs", "recall_sql", "score", "complete_docs"])
    out["per_case"] = per_case
    out["collections"] = (docs_coll, sql_coll)
    return out


def report(res: dict, split: str, project: int) -> None:
    docs_coll, sql_coll = res["collections"]
    print(f"\ndự án {project} | tập {split} | {len(res['per_case'])} câu hỏi")
    print(f"  tài liệu   top-{K_DOCS}  {docs_coll}")
    print(f"  SQL sample top-{K_SQL}  {sql_coll}  (loại mẫu trùng câu hỏi)")

    print(f"\n{'case':<9}{'gold':>5}{'docs@5':>8}{'sql@3':>7}{'điểm':>7}   mẫu dùng")
    print("-" * 66)
    for c in res["per_case"]:
        print(f"{c['id']:<9}{c['n_gold']:>5}{c['recall_docs']:>8.3f}"
              f"{c['recall_sql']:>7.3f}{c['score']:>7.3f}   {', '.join(c['samples']) or '-'}")

    print("-" * 66)
    print(f"{'TRUNG BÌNH':<9}{'':>5}{res['recall_docs']:>8.3f}"
          f"{res['recall_sql']:>7.3f}{res['score']:>7.3f}")
    print(f"\nĐIỂM TỔNG: {res['score']:.3f} / 1.000")
    print(f"  recall tài liệu@{K_DOCS} = {res['recall_docs']:.3f}"
          f" | complete@{K_DOCS} = {res['complete_docs']:.3f}")
    print(f"  recall SQL sample@{K_SQL} = {res['recall_sql']:.3f}")


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("project", type=int, nargs="?", help="id dự án")
    ap.add_argument("--split", default="dev", choices=("dev", "test"))
    ap.add_argument("--mode", default="rrf", choices=("dense", "sparse", "rrf", "wrrf"))
    args = ap.parse_args(argv)

    if args.project is None:
        print(__doc__)
        print(f"dự án có trong profile: {', '.join(map(str, CFG.projects))}")
        return 1
    if args.project not in CFG.projects:
        print(f"dự án {args.project} không có - có {CFG.projects}", file=sys.stderr)
        return 1
    if args.split == "test":
        print("! đang chấm trên TEST - chỉ chạy khi đã chốt tham số bằng dev\n")

    try:
        cases = load_split(args.split)
        # Mẫu trong index luôn là bộ dev, kể cả khi đang chấm tập test.
        indexed = load_split("dev")
        res = evaluate(cases, args.project, indexed=indexed, mode=args.mode)
    except (FileNotFoundError, ValueError) as e:
        print(e, file=sys.stderr)
        return 1
    except Exception as e:  # noqa: BLE001
        print(f"lỗi truy hồi: {e}\n  Qdrant chạy chưa? `docker compose up -d`",
              file=sys.stderr)
        return 1

    report(res, args.split, args.project)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

"""Đối soát chunk - vector - index. Chặng `verify`.

    uv run python -m src.branch_sql.offline.verify.integrity mo_ta_bang_bds_new__docx

Trả lời đúng một câu: **index đã dùng được chưa**. Không sửa gì, chỉ báo.

Ba nguồn phải khớp nhau từng `chunk_id`:

    <doc_id>.chunks.jsonl    text + metadata
    <doc_id>.vectors.npz     chunk_id -> dense vector
    Qdrant                   point mang cả dense lẫn sparse

Lệch giữa ba nguồn là kiểu hỏng không bao giờ tự lộ ra lúc chạy: truy vấn vẫn
trả về kết quả, chỉ là thiếu mất vài bảng, hoặc trả về bảng có vector nhưng
không còn text. Vì vậy mọi phép kiểm ở đây đều so ĐỦ ba nguồn chứ không chỉ đếm.

Mã thoát khác 0 khi có lỗi, để nối được vào CI hoặc vào một lệnh `&&`.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

from ...config import (
    BUDGET_MAX,
    CHUNK,
    COLLECTION,
    DENSE_VECTOR,
    EMBED_DIM,
    PROCESSED_DIR,
    SPARSE_VECTOR,
    listdir,
    rel,
)
from ..embed.encoder import load_chunks, load_vectors
from ..index.qdrant_store import get_client, point_id

# Metadata mà chặng sau và phần trích dẫn nguồn dựa vào. Thiếu một trường ở đây
# thì chunk vẫn tìm được nhưng không truy ngược được về tài liệu gốc.
REQUIRED_META = ("chunk_id", "doc_id", "table_name", "section", "element_ids",
                 "line_start", "line_end", "n_tokens")


def _fmt(names: list[str], limit: int = 3) -> str:
    head = ", ".join(str(n) for n in names[:limit])
    return head + (f" ... (+{len(names) - limit})" if len(names) > limit else "")


def check_chunks(rows: list[dict]) -> list[str]:
    """Toàn vẹn của `.chunks.jsonl`."""
    err: list[str] = []
    ids = [r["metadata"].get("chunk_id") for r in rows]

    if dup := [i for i in set(ids) if ids.count(i) > 1]:
        err.append(f"{len(dup)} chunk_id trùng: {_fmt(dup)}")
    if missing := [i for i, v in enumerate(ids) if not v]:
        err.append(f"{len(missing)} chunk không có chunk_id (dòng {_fmt(missing)})")
    if empty := [r["metadata"].get("chunk_id") for r in rows if not r["page_content"].strip()]:
        err.append(f"{len(empty)} chunk rỗng: {_fmt(empty)}")

    unit = CHUNK.budget.unit
    key = "n_tokens" if unit == "token" else "n_chars"
    if over := [r["metadata"]["table_name"] for r in rows
                if (r["metadata"].get(key) or 0) > BUDGET_MAX]:
        err.append(f"{len(over)} chunk vượt budget.max {BUDGET_MAX} {unit}: {_fmt(over)}")

    for field in REQUIRED_META:
        if lost := [r["metadata"].get("chunk_id") for r in rows
                    if r["metadata"].get(field) in (None, "")]:
            err.append(f"{len(lost)} chunk thiếu metadata '{field}': {_fmt(lost)}")
    return err


def check_vectors(rows: list[dict], vectors: dict[str, np.ndarray]) -> list[str]:
    """Toàn vẹn của `.vectors.npz` và khớp với chunk."""
    err: list[str] = []
    chunk_ids = {r["metadata"]["chunk_id"] for r in rows}

    if len(vectors) != len(rows):
        err.append(f"{len(rows)} chunk nhưng {len(vectors)} vector")
    if lost := sorted(chunk_ids - set(vectors)):
        err.append(f"{len(lost)} chunk không có vector: {_fmt(lost)}")
    if extra := sorted(set(vectors) - chunk_ids):
        err.append(f"{len(extra)} vector không thuộc chunk nào: {_fmt(extra)}")

    if not vectors:
        return err
    matrix = np.stack(list(vectors.values()))
    if matrix.shape[1] != EMBED_DIM:
        err.append(f"vector {matrix.shape[1]} chiều, profile khai {EMBED_DIM}")
    if not np.isfinite(matrix).all():
        bad = [cid for cid, v in vectors.items() if not np.isfinite(v).all()]
        err.append(f"{len(bad)} vector có NaN/Inf: {_fmt(bad)}")
    if zero := [cid for cid, v in vectors.items() if not np.abs(v).sum()]:
        err.append(f"{len(zero)} vector toàn số 0: {_fmt(zero)}")
    return err


def check_index(rows: list[dict], client) -> list[str]:
    """Point trong Qdrant phải có ĐỦ hai vector và giữ được payload."""
    err: list[str] = []
    want = {r["metadata"]["chunk_id"] for r in rows}
    ids = [point_id(c) for c in want]

    found = client.retrieve(COLLECTION, ids=ids, with_payload=True, with_vectors=True)
    by_pid = {str(p.id): p for p in found}

    if lost := [c for c in want if point_id(c) not in by_pid]:
        err.append(f"{len(lost)} chunk chưa vào index: {_fmt(lost)}")

    no_dense, no_sparse, no_text, no_meta = [], [], [], []
    for cid in want:
        p = by_pid.get(point_id(cid))
        if p is None:
            continue
        vec = p.vector or {}
        if DENSE_VECTOR not in vec:
            no_dense.append(cid)
        if SPARSE_VECTOR not in vec:
            no_sparse.append(cid)
        payload = p.payload or {}
        if not (payload.get("text") or "").strip():
            no_text.append(cid)
        if any(payload.get(f) in (None, "") for f in REQUIRED_META):
            no_meta.append(cid)

    # Hai chỉ mục nằm chung point nên "lệch tập chunk_id" biểu hiện thành
    # point thiếu một trong hai vector.
    if no_dense:
        err.append(f"{len(no_dense)} point thiếu dense vector '{DENSE_VECTOR}': {_fmt(no_dense)}")
    if no_sparse:
        err.append(f"{len(no_sparse)} point thiếu sparse vector '{SPARSE_VECTOR}': {_fmt(no_sparse)}")
    if no_text:
        err.append(f"{len(no_text)} point mất page_content: {_fmt(no_text)}")
    if no_meta:
        err.append(f"{len(no_meta)} point thiếu metadata bắt buộc: {_fmt(no_meta)}")
    return err


def run(doc_id: str, *, base: Path = PROCESSED_DIR, with_index: bool = True) -> dict:
    rows = load_chunks(doc_id, base=base)
    vectors = load_vectors(doc_id, base=base)

    errors = check_chunks(rows) + check_vectors(rows, vectors)
    indexed = None
    if with_index:
        client = get_client()
        errors += check_index(rows, client)
        indexed = client.count(COLLECTION, exact=True).count

    return {
        "doc_id": doc_id,
        "n_chunks": len(rows),
        "n_vectors": len(vectors),
        "n_points": indexed,
        "errors": errors,
    }


def report(res: dict) -> None:
    print(f"     chunk={res['n_chunks']} vector={res['n_vectors']}"
          + (f" point(collection)={res['n_points']}" if res["n_points"] is not None else ""))
    if not res["errors"]:
        print("     ✓ toàn vẹn - index dùng được")
        return
    for e in res["errors"]:
        print(f"     ✗ {e}")


def main(argv: list[str]) -> int:
    args = [a for a in argv if not a.startswith("--")]
    with_index = "--no-index" not in argv

    if not args:
        print(__doc__)
        print(f"file có sẵn trong {rel(PROCESSED_DIR)}:")
        for n in listdir(PROCESSED_DIR, "*.chunks.jsonl"):
            print(f"  - {n.removesuffix('.chunks.jsonl')}")
        return 1

    failed = 0
    for name in args:
        doc_id = name.removesuffix(".chunks.jsonl")
        try:
            res = run(doc_id, with_index=with_index)
        except (FileNotFoundError, ValueError) as e:
            print(e, file=sys.stderr)
            return 1
        print(doc_id)
        report(res)
        failed += bool(res["errors"])
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

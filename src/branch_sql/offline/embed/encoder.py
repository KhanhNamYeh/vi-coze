"""Chunk -> dense vector. Chặng `embed`.

    uv run python -m src.branch_sql.offline.embed.encoder mo_ta_bang_bds_new__docx

Đọc `<doc_id>.chunks.jsonl`, ghi `<doc_id>.vectors.npz`.

Artifact giữ đúng một thứ: ánh xạ `chunk_id -> vector`. Tách khỏi chặng `index`
để đổi vector store không phải embed lại - embed là phần đắt nhất của cả pipeline,
còn upsert thì rẻ. Cũng nhờ tách mà `verify` soi được vector trước khi chúng vào
store: NaN, sai chiều, hay lệch số lượng đều lộ ra ở đây.

Chunk vượt context limit bị TỪ CHỐI chứ không cắt cụt. Cắt cụt là kiểu hỏng tệ
nhất của RAG: chunk vẫn được index, vẫn truy hồi được, nhưng phần đuôi - thường
là chỗ chứa câu trả lời - chưa bao giờ vào vector, và không có lỗi nào báo.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

from ...config import EMBED_MODEL, PROCESSED_DIR, listdir, rel
from .dense import check_dim, context_limit, count_tokens, embed_passages


def load_chunks(doc_id: str, *, base: Path = PROCESSED_DIR) -> list[dict]:
    src = base / f"{doc_id}.chunks.jsonl"
    if not src.exists():
        raise FileNotFoundError(
            f"không thấy {rel(src)} - chạy "
            f"`python -m src.branch_sql.offline.chunk.table_chunker {doc_id}` trước"
        )
    rows = [json.loads(l) for l in src.read_text(encoding="utf-8").splitlines() if l.strip()]
    if not rows:
        raise ValueError(f"{rel(src)}: 0 chunk")
    return rows


def reject_oversized(rows: list[dict], counts: list[int]) -> None:
    """Ném lỗi nếu có chunk vượt context limit của model.

    Không tự cắt và không bỏ qua: cả hai đều làm mất tri thức trong im lặng.
    Cách sửa nằm ở chặng chunk (`budget.max`), không nằm ở đây.
    """
    limit = context_limit()
    over = [
        (r["metadata"].get("table_name") or r["metadata"]["chunk_id"], n)
        for r, n in zip(rows, counts)
        if n > limit
    ]
    if over:
        detail = ", ".join(f"{name} ({n} token)" for name, n in over[:5])
        raise ValueError(
            f"{len(over)} chunk vượt context limit {limit} token của "
            f"'{EMBED_MODEL}': {detail}\n"
            f"Hạ chunk.budget.max xuống dưới {limit} và đặt "
            f"chunk.budget.on_overflow='descend', rồi chạy lại chặng chunk."
        )


def encode(rows: list[dict]) -> tuple[list[str], np.ndarray, list[int]]:
    """-> `(chunk_id, ma trận vector, số token từng chunk)`."""
    texts = [r["page_content"] for r in rows]
    ids = [r["metadata"]["chunk_id"] for r in rows]

    counts = count_tokens(texts)
    reject_oversized(rows, counts)

    vectors = embed_passages(texts)
    check_dim(vectors)
    if len(vectors) != len(ids):
        raise ValueError(f"embed trả {len(vectors)} vector cho {len(ids)} chunk")
    return ids, vectors, counts


def write(doc_id: str, ids: list[str], vectors: np.ndarray, *,
          out_dir: Path = PROCESSED_DIR) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    dst = out_dir / f"{doc_id}.vectors.npz"
    np.savez_compressed(dst, ids=np.array(ids, dtype=object), vectors=vectors,
                        model=EMBED_MODEL)
    return dst


def load_vectors(doc_id: str, *, base: Path = PROCESSED_DIR) -> dict[str, np.ndarray]:
    """`chunk_id -> vector`. Chặng `index` đọc cái này thay vì embed lại."""
    src = base / f"{doc_id}.vectors.npz"
    if not src.exists():
        raise FileNotFoundError(
            f"không thấy {rel(src)} - chạy "
            f"`python -m src.branch_sql.offline.embed.encoder {doc_id}` trước"
        )
    data = np.load(src, allow_pickle=True)
    if str(data["model"]) != EMBED_MODEL:
        raise ValueError(
            f"{rel(src)} embed bằng '{data['model']}' nhưng profile đang dùng "
            f"'{EMBED_MODEL}' - embed lại trước khi index."
        )
    return dict(zip([str(i) for i in data["ids"]], data["vectors"]))


def check(ids: list[str], vectors: np.ndarray, counts: list[int]) -> list[str]:
    """Trả danh sách cảnh báo. Không tự sửa."""
    warn: list[str] = []
    if len(set(ids)) != len(ids):
        warn.append(f"{len(ids) - len(set(ids))} chunk_id trùng nhau")
    if not np.isfinite(vectors).all():
        warn.append(f"{int((~np.isfinite(vectors)).any(axis=1).sum())} vector có NaN/Inf")
    if (zero := int((np.abs(vectors).sum(axis=1) == 0).sum())):
        warn.append(f"{zero} vector toàn số 0 - chunk rỗng hoặc model hỏng")
    limit = context_limit()
    if near := sum(1 for n in counts if limit * 0.9 <= n <= limit):
        warn.append(f"{near} chunk nằm trong 10% cuối của context limit ({limit})")
    return warn


def report(ids: list[str], vectors: np.ndarray, counts: list[int], warn: list[str]) -> None:
    tok = sorted(counts)
    norms = np.linalg.norm(vectors, axis=1)
    print(f"     {len(ids)} vector | {vectors.shape[1]} chiều | {vectors.dtype}")
    print(f"     token min={tok[0]} p50={tok[len(tok) // 2]} max={tok[-1]} "
          f"| limit={context_limit()}")
    print(f"     chuẩn L2 min={norms.min():.4f} max={norms.max():.4f}")
    for w in warn:
        print(f"     ! {w}")


def run(doc_id: str, *, out_dir: Path = PROCESSED_DIR) -> dict:
    rows = load_chunks(doc_id)
    ids, vectors, counts = encode(rows)
    return {
        "doc_id": doc_id,
        "ids": ids,
        "vectors": vectors,
        "counts": counts,
        "path": write(doc_id, ids, vectors, out_dir=out_dir),
        "warnings": check(ids, vectors, counts),
    }


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        print(f"file có sẵn trong {rel(PROCESSED_DIR)}:")
        for n in listdir(PROCESSED_DIR, "*.chunks.jsonl"):
            print(f"  - {n.removesuffix('.chunks.jsonl')}")
        return 1

    doc_id = argv[0].removesuffix(".chunks.jsonl")
    try:
        res = run(doc_id)
    except (FileNotFoundError, ValueError) as e:
        print(e, file=sys.stderr)
        return 1

    print(f"{doc_id}.chunks.jsonl\n  -> {rel(res['path'])}")
    report(res["ids"], res["vectors"], res["counts"], res["warnings"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

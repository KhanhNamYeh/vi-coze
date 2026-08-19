"""Chunk + vector -> Qdrant. Chặng `index`.

    docker compose up -d
    uv run python -m src.branch_sql.offline.index.qdrant_store mo_ta_bang_bds_new__docx

Một collection, HAI đường tìm kiếm trên cùng tập point:

    dense   named vector, cosine, vector lấy từ `<doc_id>.vectors.npz`
    bm25    named sparse vector, dựng từ chính `page_content`

Hai đường nằm chung point nên `chunk_id` của chúng luôn khớp nhau - không có
cách nào để hai chỉ mục lệch tập tài liệu. Đó là lý do không tách BM25 ra một
store riêng dù nó rẻ hơn.

`Modifier.IDF` là BẮT BUỘC với sparse vector do FastEmbed sinh ra: bộ mã hoá cố
tình bỏ phần IDF khỏi trọng số để Qdrant tính lấy trên toàn collection. Thiếu cờ
này thì điểm BM25 sai công thức mà không có lỗi nào báo - chỉ là kết quả kém.

Point ID suy từ `chunk_id`, mà `chunk_id` băm theo NỘI DUNG: chạy lại trên cùng
dữ liệu ghi đè đúng point cũ, không nhân đôi. Chunk đổi nội dung thì thành point
mới, và point cũ thành rác - dùng `--recreate` khi đổi cách chunk.
"""

from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path

from ...config import (
    COLLECTION,
    DENSE_VECTOR,
    EMBED_DIM,
    EMBED_MODEL,
    PAYLOAD_INDEX_FIELDS,
    PROCESSED_DIR,
    QDRANT_URL,
    SPARSE_VECTOR,
    listdir,
    rel,
)
from ..embed.encoder import load_chunks, load_vectors
from ..embed.sparse import encode_passages

# Đổi giá trị này sau khi đã index sẽ sinh ra point ID khác cho cùng chunk.
NAMESPACE = uuid.UUID("6f9619ff-8b86-d011-b42d-00c04fc964ff")

UPSERT_BATCH = 64


def point_id(chunk_id: str) -> str:
    """UUID tất định từ `chunk_id`. Qdrant chỉ nhận ID kiểu uint64 hoặc UUID."""
    return str(uuid.uuid5(NAMESPACE, chunk_id))


def get_client():
    from qdrant_client import QdrantClient

    return QdrantClient(url=QDRANT_URL)


def ensure_collection(client, collection: str, *, recreate: bool = False) -> bool:
    """Tạo collection + payload index nếu chưa có. Trả True nếu vừa tạo mới."""
    from qdrant_client import models

    if recreate and client.collection_exists(collection):
        client.delete_collection(collection)

    if client.collection_exists(collection):
        info = client.get_collection(collection)
        vectors = info.config.params.vectors or {}
        if DENSE_VECTOR not in vectors:
            raise ValueError(
                f"collection '{collection}' không có vector tên '{DENSE_VECTOR}'. "
                "Chạy lại với --recreate."
            )
        if (dim := vectors[DENSE_VECTOR].size) != EMBED_DIM:
            raise ValueError(
                f"collection '{collection}' đang có {dim} chiều nhưng model cho "
                f"{EMBED_DIM} chiều. Đổi model thì phải đổi index.collection và index lại."
            )
        sparse = info.config.params.sparse_vectors or {}
        if SPARSE_VECTOR in sparse and sparse[SPARSE_VECTOR].modifier != models.Modifier.IDF:
            raise ValueError(
                f"sparse vector '{SPARSE_VECTOR}' thiếu Modifier.IDF - điểm BM25 "
                "sẽ sai công thức. Chạy lại với --recreate."
            )
        return False

    client.create_collection(
        collection_name=collection,
        vectors_config={
            DENSE_VECTOR: models.VectorParams(size=EMBED_DIM, distance=models.Distance.COSINE),
        },
        sparse_vectors_config={
            # IDF tính phía server nên tự cập nhật khi nạp thêm document.
            SPARSE_VECTOR: models.SparseVectorParams(modifier=models.Modifier.IDF),
        },
    )
    # Thiếu payload index thì filter là quét toàn bộ collection.
    for field in PAYLOAD_INDEX_FIELDS:
        client.create_payload_index(
            collection_name=collection,
            field_name=field,
            field_schema=models.PayloadSchemaType.KEYWORD,
        )
    return True


def load_parents(doc_id: str, *, base: Path = PROCESSED_DIR) -> dict[str, str]:
    """`chunk_id của cha -> page_content`. Rỗng nếu không phải chế độ parent_child.

    Cha đi thẳng vào payload của con thay vì nằm ở một collection riêng: quan hệ
    ở đây là 1-1 nên không có gì bị nhân bản, và truy hồi chỉ tốn MỘT vòng gọi -
    khớp bằng câu hỏi rồi trả về cả mẫu, không phải tra thêm docstore.
    """
    src = base / f"{doc_id}.parents.jsonl"
    if not src.exists():
        return {}
    rows = [json.loads(l) for l in src.read_text(encoding="utf-8").splitlines() if l.strip()]
    return {r["metadata"]["chunk_id"]: r["page_content"] for r in rows}


def build_points(rows: list[dict], vectors: dict[str, list[float]],
                 parents: dict[str, str] | None = None):
    """Chunk + vector -> PointStruct, sparse dựng ngay tại đây."""
    from qdrant_client import models

    texts = [r["page_content"] for r in rows]
    sparse = encode_passages(texts)

    points = []
    for row, sv in zip(rows, sparse):
        meta = row["metadata"]
        cid = meta["chunk_id"]
        if cid not in vectors:
            raise ValueError(
                f"chunk_id '{cid}' không có vector trong .vectors.npz - "
                "chạy lại chặng embed sau khi đổi chunk."
            )
        points.append(models.PointStruct(
            id=point_id(cid),
            vector={
                DENSE_VECTOR: vectors[cid].tolist(),
                SPARSE_VECTOR: models.SparseVector(indices=sv.indices, values=sv.values),
            },
            # `text` giữ nguyên page_content để trả về nguyên văn; metadata trải
            # phẳng để filter theo `table_name`/`section` không phải nested key.
            # `parent_text` là nội dung ĐẦY ĐỦ để trả cho LLM khi con khớp.
            payload={
                "text": row["page_content"],
                **meta,
                **({"parent_text": parents[meta["parent_chunk_id"]]}
                   if parents and meta.get("parent_chunk_id") in parents else {}),
            },
        ))
    return points


def index(doc_id: str, *, collection: str = COLLECTION, recreate: bool = False,
          base: Path = PROCESSED_DIR) -> dict:
    """Đọc chunk + vector của một tài liệu rồi upsert. Chạy lại không nhân đôi."""
    rows = load_chunks(doc_id, base=base)
    vectors = load_vectors(doc_id, base=base)
    if len(vectors) != len(rows):
        raise ValueError(
            f"{len(rows)} chunk nhưng {len(vectors)} vector - embed và chunk lệch nhau, "
            "chạy lại chặng embed."
        )

    parents = load_parents(doc_id, base=base)
    client = get_client()
    created = ensure_collection(client, collection, recreate=recreate)
    points = build_points(rows, vectors, parents)

    for i in range(0, len(points), UPSERT_BATCH):
        client.upsert(collection, points=points[i : i + UPSERT_BATCH], wait=True)

    return {
        "doc_id": doc_id,
        "collection": collection,
        "created": created,
        "n_points": len(points),
        "n_parents": len(parents),
        "total": client.count(collection, exact=True).count,
    }


def report(res: dict) -> None:
    print(f"     collection '{res['collection']}' {'vừa tạo' if res['created'] else 'đã có'}"
          f" | dense='{DENSE_VECTOR}' ({EMBED_DIM}d) + sparse='{SPARSE_VECTOR}' (IDF)")
    print(f"     upsert {res['n_points']} point"
          + (f" (kèm {res['n_parents']} cha trong payload)" if res["n_parents"] else "")
          + f" | tổng trong collection: {res['total']}")
    print(f"     model: {EMBED_MODEL}")


def main(argv: list[str]) -> int:
    args = [a for a in argv if not a.startswith("--")]
    recreate = "--recreate" in argv

    if not args:
        print(__doc__)
        print(f"file có sẵn trong {rel(PROCESSED_DIR)}:")
        for n in listdir(PROCESSED_DIR, "*.vectors.npz"):
            print(f"  - {n.removesuffix('.vectors.npz')}")
        return 1

    try:
        for i, name in enumerate(args):
            doc_id = name.removesuffix(".chunks.jsonl").removesuffix(".vectors.npz")
            res = index(doc_id, collection=COLLECTION, recreate=recreate and i == 0)
            print(f"{doc_id}\n  -> qdrant {QDRANT_URL}")
            report(res)
    except (FileNotFoundError, ValueError) as e:
        print(e, file=sys.stderr)
        return 1
    except Exception as e:  # noqa: BLE001
        print(f"lỗi Qdrant: {e}\n  Qdrant chạy chưa? `docker compose up -d`", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

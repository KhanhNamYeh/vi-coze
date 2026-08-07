"""Embed chunk rồi upsert lên Qdrant.

    docker compose up -d
    uv run python -m src.retrieval.store mo_ta_bang_bds_new.chunks.jsonl
"""

from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path

from langchain_core.documents import Document

from ..config_sql import (
    ARTIFACT_DIR,
    COLLECTION,
    DENSE_VECTOR,
    EMBED_BATCH,
    EMBED_DIM,
    EMBED_MODEL,
    PAYLOAD_INDEX_FIELDS,
    QDRANT_URL,
    SPARSE_MODEL,
    SPARSE_VECTOR,
    listdir,
    rel,
    require,
    resolve,
)
from .embeddings import embed_passages
from .sparse import encode_passages

# Đổi giá trị này sau khi đã index sẽ sinh ra point ID khác cho cùng chunk.
NAMESPACE = uuid.UUID("6f9619ff-8b86-d011-b42d-00c04fc964ff")


def point_id(meta: dict) -> str:
    """UUID tất định. Qdrant chỉ nhận point ID kiểu uint64 hoặc UUID."""
    key = f"{meta['doc_id']}|{meta['no']}|{meta['part']}"
    return str(uuid.uuid5(NAMESPACE, key))


def load_chunks(name: str | Path, *, base: Path = ARTIFACT_DIR) -> list[Document]:
    src = require(resolve(name, base), base)
    docs = [
        Document(**json.loads(line))
        for line in src.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if not docs:
        raise ValueError(f"{rel(src)}: 0 chunk - chạy chunking trước")
    return docs


def get_client():
    from qdrant_client import QdrantClient

    return QdrantClient(url=QDRANT_URL)


def ensure_collection(client, *, recreate: bool = False) -> bool:
    """Tạo collection + payload index nếu chưa có. Trả True nếu vừa tạo mới."""
    from qdrant_client import models

    exists = client.collection_exists(COLLECTION)
    if exists and recreate:
        client.delete_collection(COLLECTION)
        exists = False
    if exists:
        info = client.get_collection(COLLECTION)
        vectors = info.config.params.vectors or {}
        if DENSE_VECTOR not in vectors:
            raise ValueError(
                f"collection '{COLLECTION}' không có vector tên '{DENSE_VECTOR}' "
                f"(schema cũ dùng vector không tên). Chạy lại với --recreate."
            )
        dim = vectors[DENSE_VECTOR].size
        if dim != EMBED_DIM:
            raise ValueError(
                f"collection '{COLLECTION}' đang có {dim} chiều nhưng model cho "
                f"{EMBED_DIM} chiều. Đổi model thì phải đổi tên collection và index lại."
            )
        return False

    client.create_collection(
        collection_name=COLLECTION,
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
            collection_name=COLLECTION,
            field_name=field,
            field_schema=models.PayloadSchemaType.KEYWORD,
        )
    return True


def index(docs: list[Document], *, recreate: bool = False) -> dict:
    """Embed rồi upsert. Chạy lại trên cùng dữ liệu không nhân đôi điểm."""
    from qdrant_client import models

    client = get_client()
    created = ensure_collection(client, recreate=recreate)

    total = 0
    for i in range(0, len(docs), EMBED_BATCH):
        batch = docs[i : i + EMBED_BATCH]
        texts = [d.page_content for d in batch]
        dense = embed_passages(texts)
        sparse = encode_passages(texts)
        client.upsert(
            collection_name=COLLECTION,
            points=[
                models.PointStruct(
                    id=point_id(d.metadata),
                    vector={
                        DENSE_VECTOR: dv,
                        SPARSE_VECTOR: models.SparseVector(
                            indices=sv.indices, values=sv.values
                        ),
                    },
                    # giữ cả text để search trả về nội dung, không chỉ id
                    payload={
                        **d.metadata,
                        "text": d.page_content,
                        "embed_model": EMBED_MODEL,
                        "sparse_model": SPARSE_MODEL,
                    },
                )
                for d, dv, sv in zip(batch, dense, sparse)
            ],
            wait=True,
        )
        total += len(batch)
        print(f"     upsert {total}/{len(docs)}")

    return {
        "collection": COLLECTION,
        "created": created,
        "indexed": total,
        "count": client.count(COLLECTION, exact=True).count,
    }


def main(argv: list[str]) -> int:
    args = [a for a in argv if not a.startswith("--")]
    recreate = "--recreate" in argv

    if not args:
        print(__doc__)
        print(f"file có sẵn trong {rel(ARTIFACT_DIR)}:")
        for n in listdir(ARTIFACT_DIR, "*.chunks.jsonl"):
            print(f"  - {n}")
        return 1

    try:
        docs = load_chunks(args[0])
    except (FileNotFoundError, ValueError) as e:
        print(e, file=sys.stderr)
        return 1

    print(f"{args[0]}\n     {len(docs)} chunk")
    print(f"     dense  {EMBED_MODEL} ({EMBED_DIM} chiều)")
    print(f"     sparse {SPARSE_MODEL}")
    try:
        result = index(docs, recreate=recreate)
    except Exception as e:  # noqa: BLE001 - in gọn thay vì traceback
        print(f"\nlỗi khi kết nối/ghi Qdrant ({QDRANT_URL}): {e}", file=sys.stderr)
        print("Qdrant đã chạy chưa?  docker compose up -d", file=sys.stderr)
        return 1

    print(f"  -> collection '{result['collection']}'"
          f" ({'vừa tạo' if result['created'] else 'đã có sẵn'})")
    print(f"     đã index {result['indexed']} | tổng trong collection: {result['count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

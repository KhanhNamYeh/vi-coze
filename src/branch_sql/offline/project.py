"""Chạy trọn một DỰ ÁN qua mọi chặng offline.

    uv run python -m src.branch_sql.offline.project 1
    uv run --extra pdf python -m src.branch_sql.offline.project 2 --recreate

Một dự án là một hộp đen: nó chỉ thấy các bộ tri thức khai `project` trỏ về nó,
ghi artifact vào `data/processed/<kb>/p<id>/`, và index vào collection riêng.
Hai dự án không dùng chung một collection nào - `KnowledgeCfg` chặn điều đó ngay
lúc nạp profile.

Mỗi bộ tri thức đi qua sáu chặng với ĐÚNG khối `chunk` của riêng nó:

    parse -> extract -> link -> chunk -> embed -> index

Bộ tri thức khai `project: [1, 2]` được xử lý lại cho từng dự án chứ không dùng
chung kết quả. Tốn thêm một lượt build, đổi lại là cách ly thật.
"""

from __future__ import annotations

import os
import sys

from ..config import CFG, PROCESSED_DIR, QDRANT_URL, rel
from .chunk import table_chunker as chunking
from .embed import encoder as embedding
from .extract import block_extract as extracting, blocks
from .index import qdrant_store as indexing
from .link import hierarchy as linking
from .parse import doc_parse as parsing


def run_knowledge(k, *, project: int, recreate: bool = False) -> dict:
    """Một bộ tri thức -> artifact + point trong collection của dự án."""
    doc = parsing.parse(k.source)
    doc_id = doc.metadata["doc_id"]
    md_path = parsing.write_markdown(doc, out_dir=PROCESSED_DIR)

    ir = extracting.build_ir(
        blocks.split(doc.page_content),
        doc_id=doc_id,
        title=doc.metadata.get("title"),
        source_name=doc.metadata.get("source_name"),
        warnings=doc.metadata["warnings"],
    )
    extracting.write(ir, out_dir=PROCESSED_DIR)

    ir = linking.link(ir)
    linking.write(ir, out_dir=PROCESSED_DIR)

    cfg = CFG.chunk_of(k)
    chunks, parents = chunking.build(ir, cfg=cfg)
    chunk_path = chunking.write_chunks(chunks, out_dir=PROCESSED_DIR, doc_id=doc_id)
    if parents:
        chunking.write_chunks(parents, out_dir=PROCESSED_DIR, doc_id=doc_id, suffix="parents")

    emb = embedding.run(doc_id, out_dir=PROCESSED_DIR)
    idx = indexing.index(doc_id, collection=k.collection_for(project),
                         recreate=recreate, base=PROCESSED_DIR)

    return {
        "knowledge": k.id, "doc_id": doc_id, "md": md_path, "chunk_path": chunk_path,
        "n_elements": len(ir["elements"]), "n_chunks": len(chunks),
        "n_parents": len(parents), "mode": cfg.mode, "index": idx,
        "warnings": [*ir["warnings"], *chunking.check(chunks, cfg=cfg, parents=parents),
                     *emb["warnings"]],
    }


def main(argv: list[str]) -> int:
    args = [a for a in argv if not a.startswith("--")]
    recreate = "--recreate" in argv

    if not args:
        print(__doc__)
        print(f"dự án có trong profile: {', '.join(map(str, CFG.projects))}")
        return 1

    project = int(args[0])
    if project not in CFG.projects:
        print(f"dự án {project} không có trong profile - có {CFG.projects}", file=sys.stderr)
        return 1
    if os.getenv("VI_COZE_PROJECT") != str(project):
        print(f"đặt VI_COZE_PROJECT={project} rồi chạy lại - đường dẫn artifact "
              f"suy ra lúc nạp profile", file=sys.stderr)
        return 1

    items = CFG.knowledge_of(project)
    print(f"dự án {project} | {len(items)} bộ tri thức | artifact: {rel(PROCESSED_DIR)}")

    failed = 0
    for k in items:
        try:
            res = run_knowledge(k, project=project, recreate=recreate)
        except Exception as e:  # noqa: BLE001
            print(f"\n  {k.id}: LỖI {e}", file=sys.stderr)
            failed += 1
            continue
        idx = res["index"]
        print(f"\n  {res['knowledge']} ({res['doc_id']})")
        print(f"    chunk  -> {rel(res['chunk_path'])} | chế độ {res['mode']}"
              f" | {res['n_chunks']} chunk"
              + (f" + {res['n_parents']} cha" if res["n_parents"] else ""))
        print(f"    index  -> {idx['collection']} | {idx['n_points']} point"
              f" | tổng {idx['total']}")
        for w in res["warnings"]:
            print(f"    ! {w}")
    print(f"\nqdrant: {QDRANT_URL}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

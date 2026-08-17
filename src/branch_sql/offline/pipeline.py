"""Pipeline offline của nhánh SQL. Điều phối các chặng trong `offline/`.

    uv run python -m src.branch_sql.offline "Mô tả bảng BĐS (NEW).docx"

Chỉ cần tên file, mặc định tìm trong `config.RAW_DIR`. Artifact ghi ra
`config.PROCESSED_DIR`:

    <doc_id>.md                    markdown đã dựng cấu trúc, đã làm sạch
    <doc_id>.chunks.jsonl          chunk kèm metadata
    knowledge/sql_knowledge_map.*  knowledge graph (chỉ khi có cờ --kg)

Mặc định chạy hết luồng, bao gồm embed + đẩy lên Qdrant:

    parse -> chunk -> embed (dense + bm25) -> upsert Qdrant

Cờ:

    --no-index   dừng sau bước chunk. Không nạp model 2,2 GB, chạy ~10 giây —
                 dùng khi tune tham số chunking.
    --kg         chạy thêm bước dựng knowledge graph từ markdown. Bước này gọi
                 LLM qua endpoint OpenAI-compatible (mặc định ollama ở
                 localhost:11434) nên tách khỏi luồng mặc định.

Trừ cờ --kg, pipeline chạy hoàn toàn tách khỏi đường request: không cần API,
không gọi LLM. Nối bằng LCEL nên bọc vào worker sau này không phải sửa các bước.
"""

from __future__ import annotations

import sys
from pathlib import Path

from langchain_core.documents import Document
from langchain_core.runnables import Runnable, RunnableLambda

from ..config import PROCESSED_DIR, RAW_DIR, ROOT, listdir, rel
from .chunk import table_chunker as chunking
from .parse import docx_parse as parse


def build_chain(
    *,
    source_dir: Path = RAW_DIR,
    out_dir: Path = PROCESSED_DIR,
    do_index: bool = True,
    do_kg: bool = False,
) -> Runnable[str, dict]:
    """tên file -> {"markdown": Path, "chunks": list[Document], ...}"""

    def _parse(name: str) -> Document:
        doc = parse.parse(name, base=source_dir)
        md_path = parse.write_markdown(doc, out_dir=out_dir)
        # tương đối, vì payload lên vector store không được chứa path máy build
        doc.metadata["source_path"] = (
            md_path.relative_to(ROOT).as_posix() if md_path.is_relative_to(ROOT) else md_path.name
        )
        doc.metadata["markdown_path"] = md_path
        return doc

    def _chunk(doc: Document) -> dict:
        chunks = chunking.split(doc)
        warnings = list(doc.metadata.get("warnings", [])) + chunking.check(chunks)
        chunks_path = chunking.write_chunks(
            chunks, out_dir=out_dir, doc_id=doc.metadata["doc_id"]
        )
        return {
            "doc_id": doc.metadata["doc_id"],
            "title": doc.metadata.get("title"),
            "markdown": doc.metadata["markdown_path"],
            "chunks_path": chunks_path,
            "chunks": chunks,
            "n_sections": doc.metadata.get("n_sections"),
            "n_tables": doc.metadata.get("n_tables"),
            "warnings": warnings,
        }

    def _knowledge(result: dict) -> dict:
        # import muộn: kéo theo openai/networkx/pyvis, chỉ cần khi có cờ --kg
        from .link import knowledge_graph as knowledge

        result["knowledge"] = knowledge.build(result["markdown"])
        return result

    def _index(result: dict) -> dict:
        # import muộn để --no-index không phải nạp model
        from .index import qdrant_store as store

        result["indexed"] = store.index(result["chunks"])
        return result

    chain = RunnableLambda(_parse, name="parse") | RunnableLambda(_chunk, name="chunk")
    if do_kg:
        chain = chain | RunnableLambda(_knowledge, name="knowledge")
    return chain | RunnableLambda(_index, name="index") if do_index else chain


def run(name: str, **kw) -> dict:
    return build_chain(**kw).invoke(name)


def main(argv: list[str]) -> int:
    names = [a for a in argv if not a.startswith("--")]
    do_index = "--no-index" not in argv
    do_kg = "--kg" in argv

    if not names:
        print(__doc__)
        print(f"file có sẵn trong {rel(RAW_DIR)}:")
        for n in listdir(RAW_DIR):
            print(f"  - {n}")
        return 1

    chain = build_chain(do_index=do_index, do_kg=do_kg)
    try:
        results = chain.batch(names) if len(names) > 1 else [chain.invoke(names[0])]
    except (FileNotFoundError, ValueError) as e:
        print(e, file=sys.stderr)
        return 1
    except Exception as e:  # noqa: BLE001
        print(f"\nlỗi ở bước index: {e}", file=sys.stderr)
        print("Qdrant đã chạy chưa?  docker compose up -d", file=sys.stderr)
        print("Chỉ muốn parse+chunk thì thêm cờ --no-index", file=sys.stderr)
        return 1

    failed = 0
    for r in results:
        print(f"\n{r['title']}")
        print(f"  md     -> {rel(r['markdown'])}")
        print(f"  chunks -> {rel(r['chunks_path'])}")
        print(f"  {r['n_sections']} nhóm | {r['n_tables']} bảng")
        chunking.report(r["chunks"], r["warnings"])
        if kg := r.get("knowledge"):
            print(f"  kg     -> {rel(kg['json'])}"
                  f" | {kg['n_nodes']} node, {kg['n_edges']} cạnh")
        if idx := r.get("indexed"):
            print(f"  index  -> collection '{idx['collection']}'"
                  f" | {idx['count']} điểm (dense + bm25)")
        if not r["chunks"]:
            failed += 1
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

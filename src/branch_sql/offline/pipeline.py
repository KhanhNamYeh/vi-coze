"""Pipeline offline nhánh SQL: raw -> parse -> extract -> link -> chunk.

    uv run python -m src.branch_sql.offline "Mô tả bảng BĐS (NEW).docx"

Đầu vào được tìm trong `data/raw/sql/`; artifact ghi vào `data/processed/sql/`:

    <doc_id>.md             canonical Markdown, artifact duy nhất của parse
    <doc_id>.extract.json   independent structured elements
    <doc_id>.linked.json    element đã gắn vào cây cha-con của tài liệu
    <doc_id>.chunks.jsonl   chunk kèm metadata, sẵn sàng cho embed

Pipeline này kết thúc ở `chunk`: không embed, index, dựng knowledge graph hay
gọi LLM. Cả bốn chặng đều tất định - cùng đầu vào cho ra cùng artifact.
"""

from __future__ import annotations

import sys
from pathlib import Path

from langchain_core.documents import Document
from langchain_core.runnables import Runnable, RunnableLambda

from ..config import PROCESSED_DIR, RAW_DIR, listdir, rel
from .chunk import table_chunker as chunking
from .extract import block_extract as extracting, blocks
from .link import hierarchy as linking
from .parse import doc_parse as parsing


def build_chain(
    *,
    source_dir: Path = RAW_DIR,
    out_dir: Path = PROCESSED_DIR,
) -> Runnable[str, dict]:
    """Tên file trong raw -> kết quả của ba chặng trong processed."""

    def _parse(name: str) -> Document:
        doc = parsing.parse(name, base=source_dir)
        # Chỉ truyền nội bộ để chặng sau biết file vừa ghi; không có sidecar
        # metadata và không đưa đường dẫn máy build vào extract envelope.
        doc.metadata["markdown_path"] = parsing.write_markdown(doc, out_dir=out_dir)
        return doc

    def _extract(doc: Document) -> dict:
        metadata = doc.metadata
        parsed_blocks = blocks.split(doc.page_content)
        ir = extracting.build_ir(
            parsed_blocks,
            doc_id=metadata["doc_id"],
            title=metadata.get("title"),
            source_name=metadata.get("source_name"),
            warnings=metadata["warnings"],
        )
        return {
            "doc_id": ir["doc_id"],
            "title": ir["title"],
            "markdown": metadata["markdown_path"],
            "roles": blocks.count_roles(parsed_blocks),
            "extract_path": extracting.write(ir, out_dir=out_dir),
            "ir": ir,
            "warnings": ir["warnings"],
        }

    def _link(result: dict) -> dict:
        ir = linking.link(result["ir"])
        result["ir"] = ir
        result["link_path"] = linking.write(ir, out_dir=out_dir)
        result["warnings"] = ir["warnings"]
        return result

    def _chunk(result: dict) -> dict:
        chunks = chunking.split(result["ir"])
        result["chunks"] = chunks
        result["chunk_path"] = chunking.write_chunks(
            chunks, out_dir=out_dir, doc_id=result["doc_id"]
        )
        result["warnings"] = [*result["warnings"], *chunking.check(chunks)]
        return result

    return (
        RunnableLambda(_parse, name="parse")
        | RunnableLambda(_extract, name="extract")
        | RunnableLambda(_link, name="link")
        | RunnableLambda(_chunk, name="chunk")
    )


def run(name: str, **kwargs) -> dict:
    return build_chain(**kwargs).invoke(name)


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        print(f"file có sẵn trong {rel(RAW_DIR)}:")
        for name in listdir(RAW_DIR):
            print(f"  - {name}")
        return 1

    chain = build_chain()
    try:
        results = chain.batch(argv) if len(argv) > 1 else [chain.invoke(argv[0])]
    except (FileNotFoundError, ImportError, ValueError) as error:
        print(error, file=sys.stderr)
        return 1
    except Exception as error:  # noqa: BLE001
        print(f"\nlỗi pipeline: {error}", file=sys.stderr)
        return 1

    failed = 0
    for result in results:
        ir = result["ir"]
        print(f"\n{result['title']}")
        print(f"  parse   -> {rel(result['markdown'])}")
        print(
            f"  extract -> {rel(result['extract_path'])} | {len(ir['elements'])} phần tử"
            f" | {', '.join(f'{n} {role}' for role, n in result['roles'].items())}"
        )
        attached = sum(1 for el in ir["elements"] if el.get("parent_id"))
        roots = sum(1 for el in ir["elements"] if not el.get("parent_id"))
        print(
            f"  link    -> {rel(result['link_path'])} | {attached} phần tử có cha"
            f" | {roots} gốc"
        )
        sizes = sorted(c.metadata["n_tokens"] or 0 for c in result["chunks"])
        print(
            f"  chunk   -> {rel(result['chunk_path'])} | {len(sizes)} chunk"
            f" | p50={sizes[len(sizes) // 2] if sizes else 0} token"
        )
        for warning in result["warnings"]:
            print(f"  ! {warning}")
        if not ir["elements"]:
            failed += 1
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

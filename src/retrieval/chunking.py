"""markdown -> chunks. Bước `split` của pipeline offline.

    uv run python -m src.retrieval.chunking mo_ta_bang_bds_new.md

Chỉ cần tên file — mặc định tìm trong `config.ARTIFACT_DIR`, ghi .chunks.jsonl
cạnh file .md.

Cắt theo cấu trúc, không cắt theo độ dài: một bảng = một chunk, overlap = 0.
Tham số ở `config_sql.py`, phần `---- chunking ----`.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from langchain_core.documents import Document
from langchain_core.runnables import Runnable, RunnableLambda
from langchain_text_splitters import MarkdownHeaderTextSplitter

from ..config_sql import (
    ARTIFACT_DIR,
    HEADERS_TO_SPLIT_ON,
    MAX_CHARS,
    MIN_CHARS,
    ROOT,
    STRIP_HEADERS,
    listdir,
    rel,
    require,
    resolve,
)
from ..schemas import ChunkMeta

TABLE_PREFIX = re.compile(r"^Bảng\s+", re.IGNORECASE)

_splitter = MarkdownHeaderTextSplitter(
    headers_to_split_on=HEADERS_TO_SPLIT_ON,
    strip_headers=STRIP_HEADERS,
)


def split(doc: Document) -> list[Document]:
    """Document markdown -> list[Document]. Chỉ cắt, kiểm tra ở `check()`."""
    doc_id = doc.metadata.get("doc_id", "unknown")
    source_path = doc.metadata.get("source_path")

    chunks: list[Document] = []
    per_section: dict[str | None, int] = {}

    for part in _splitter.split_text(doc.page_content):
        table = part.metadata.get("table")
        if not table:
            # phần mở đầu của một nhóm, chưa thuộc bảng nào
            continue

        section = part.metadata.get("section")
        per_section[section] = per_section.get(section, 0) + 1
        text = part.page_content.strip()

        meta = ChunkMeta.build(
            text=text,
            doc_id=doc_id,
            section=section,
            table_name=TABLE_PREFIX.sub("", table).strip(),
            no=f"{len(per_section)}.{per_section[section]}",
            source_path=source_path,
        )
        chunks.append(Document(page_content=text, metadata=meta.model_dump()))

    return chunks


def check(chunks: list[Document], *, max_chars: int = MAX_CHARS, min_chars: int = MIN_CHARS) -> list[str]:
    """Trả danh sách cảnh báo. Không tự sửa."""
    warn: list[str] = []
    if not chunks:
        return ["0 chunk - markdown thiếu heading `##`"]

    seen: dict[str, str] = {}
    for c in chunks:
        m = c.metadata
        name = m["table_name"]
        if m["n_chars"] > max_chars:
            warn.append(f"{name}: {m['n_chars']} ký tự > trần {max_chars} - cần tách")
        if m["n_chars"] < min_chars:
            warn.append(f"{name}: {m['n_chars']} ký tự < {min_chars} - chunk quá nhỏ")
        if m["content_hash"] in seen:
            warn.append(f"{name} trùng nội dung với {seen[m['content_hash']]}")
        seen[m["content_hash"]] = name
    return warn


def load_markdown(name: str | Path, *, base: Path = ARTIFACT_DIR) -> Document:
    src = require(resolve(name, base), base)
    rel = src.relative_to(ROOT).as_posix() if src.is_relative_to(ROOT) else src.name
    return Document(
        page_content=src.read_text(encoding="utf-8"),
        metadata={"doc_id": src.stem, "source_path": rel, "title": src.stem},
    )


def write_chunks(chunks: list[Document], *, out_dir: Path = ARTIFACT_DIR, doc_id: str) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    dst = out_dir / f"{doc_id}.chunks.jsonl"
    with dst.open("w", encoding="utf-8") as f:
        for c in chunks:
            row = {"page_content": c.page_content, "metadata": c.metadata}
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return dst


def as_runnable() -> Runnable[Document, list[Document]]:
    """Bước `split` để nối vào LCEL chain."""
    return RunnableLambda(split, name="chunk")


def report(chunks: list[Document], warn: list[str]) -> None:
    if not chunks:
        print("     ! 0 chunk - markdown thiếu heading `##`")
        return
    sizes = sorted(c.metadata["n_chars"] for c in chunks)
    print(f"     {len(chunks)} chunk | min={sizes[0]} p50={sizes[len(sizes) // 2]} max={sizes[-1]} ký tự")
    print(f"     có table_name: {sum(1 for c in chunks if c.metadata['table_name'])}/{len(chunks)}")
    for w in warn:
        print(f"     ! {w}")
    for c in chunks:
        m = c.metadata
        print(f"       {m['no']:<5} {m['chunk_id']}  {m['n_chars']:>5}  {m['table_name']}")


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        print(f"file có sẵn trong {rel(ARTIFACT_DIR)}:")
        for n in listdir(ARTIFACT_DIR, "*.md"):
            print(f"  - {n}")
        return 1

    try:
        doc = load_markdown(argv[0])
    except FileNotFoundError as e:
        print(e, file=sys.stderr)
        return 1

    chunks = split(doc)
    warn = check(chunks)
    dst = write_chunks(chunks, doc_id=doc.metadata["doc_id"])

    print(f"{doc.metadata['doc_id']}.md\n  -> {rel(dst)}")
    report(chunks, warn)
    return 1 if not chunks else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

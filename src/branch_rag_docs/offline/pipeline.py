"""Pipeline offline của nhánh PDF. Điều phối các chặng trong `offline/`.

    uv sync --extra rag_docs
    uv run python -m src.branch_rag_docs.offline "[Reading]-RAG-System.pdf"

Chỉ cần tên file, mặc định tìm trong `config.RAW_DIR`. Artifact ghi ra
`config.PROCESSED_DIR`:

    pdf_extract.jsonl       block kèm số trang           (chặng parse)
    merged_documents.jsonl  block + caption hình         (chặng extract)
    chunked.jsonl           chunk                        (chặng chunk)

Cờ:

    --no-index   dừng sau bước chunk, không nạp model embedding
    --images     chạy thêm chặng tách hình + sinh caption, rồi gộp vào text.
                 Tách riêng vì captioner nạp thêm model BLIP.

Đối xứng với `src/branch_sql/offline/pipeline.py` — cùng cách nối chặng, cùng
cách in kết quả. Khác ở chỗ nhánh này chưa có chặng `link`, và chặng `verify`
phải chạy tay.
"""

from __future__ import annotations

import sys
from pathlib import Path

from .. import config


def run(name: str, *, do_index: bool = True, do_images: bool = False) -> dict:
    """tên file -> {"blocks": Path, "chunks": Path, ...}"""
    from .chunk.text_chunker import ChunkConfig, process_chunking
    from .parse.pdf_parse import convert_pdf

    src = config.require(config.resolve(name, config.RAW_DIR), config.RAW_DIR)
    config.PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    result: dict = {"source": src}

    # ---- chặng 1: parse
    convert_pdf(src, config.BLOCKS)
    result["blocks"] = config.BLOCKS
    text_input = config.BLOCKS

    # ---- chặng 2: extract (chỉ khi có hình)
    if do_images:
        from .extract.merge_documents import merge_documents
        from .parse.image_captioner import main as caption_main  # noqa: F401
        from .parse.image_extractor import main as extract_main  # noqa: F401

        merge_documents(
            config.BLOCKS, config.IMAGE_CAPTIONS, config.IMAGE_META, config.MERGED
        )
        result["merged"] = config.MERGED
        text_input = config.MERGED

    # ---- chặng 4: chunk
    process_chunking(
        text_input,
        config.CHUNKS,
        ChunkConfig(chunk_size=config.CHUNK_SIZE, chunk_overlap=config.CHUNK_OVERLAP),
    )
    result["chunks"] = config.CHUNKS

    # ---- chặng 5: embed + index
    if do_index:
        from .index.chroma_store import build_index

        build_index(config.CHUNKS, config.CHROMA_DIR, config.EMBED_MODEL)
        result["index"] = config.CHROMA_DIR

    return result


def main(argv: list[str]) -> int:
    names = [a for a in argv if not a.startswith("--")]
    do_index = "--no-index" not in argv
    do_images = "--images" in argv

    if not names:
        print(__doc__)
        print(f"file có sẵn trong {config.rel(config.RAW_DIR)}:")
        for n in config.listdir(config.RAW_DIR):
            print(f"  - {n}")
        return 1

    try:
        result = run(names[0], do_index=do_index, do_images=do_images)
    except FileNotFoundError as e:
        print(e, file=sys.stderr)
        return 1
    except ImportError as e:
        print(f"thiếu thư viện: {e}", file=sys.stderr)
        print("chạy:  uv sync --extra rag_docs", file=sys.stderr)
        return 1

    print(f"\n{Path(result['source']).name}")
    print(f"  blocks -> {config.rel(result['blocks'])}")
    if merged := result.get("merged"):
        print(f"  merged -> {config.rel(merged)}")
    print(f"  chunks -> {config.rel(result['chunks'])}")
    if idx := result.get("index"):
        print(f"  index  -> {config.rel(idx)} | collection '{config.COLLECTION}'")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

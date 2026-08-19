"""markdown -> block. Nửa đầu của chặng `extract`: cấu trúc, ID, khoảng dòng.

    uv run python -m src.branch_sql.offline.extract.blocks mo_ta_bang_bds_new__docx.md

Ranh giới với `parse`: `parse` biết .docx và .pdf hỏng theo kiểu gì và trả về
markdown; từ markdown trở đi là việc của `extract`. Nhờ vậy `parse` là chặng duy
nhất phụ thuộc định dạng nguồn, còn file này chỉ biết CommonMark - cùng một luật
cho mọi tài liệu, mọi ngôn ngữ.

KHÔNG ghi ra file. Artifact của `extract` là `.extract.json`; block là bước trung
gian, và nó là hàm thuần của (`.md`, `extract.heading_roles`) nên ghi `.blocks.json`
chỉ tạo một bản cache 40 KB cho một phép tính 40 ms, kèm một schema nữa phải giữ
đồng bộ. Lệnh trên là công cụ SOI: in cấu trúc rồi thoát.

Chỉ trả lời "tài liệu được cấu tạo thế nào", không đọc nội dung bên trong block.
Việc lấy nội dung là của `block_extract.py`.

Việc tách block do `markdown-it-py` làm, không tự viết regex: nó là bộ phân tích
CommonMark đầy đủ nên xử đúng những ca mà regex sai — khối code có dấu ``` chứa
dòng trông như bảng, heading kiểu gạch dưới, danh sách lồng, HTML block, dấu `|`
được escape trong ô. Token của nó có sẵn `map` là khoảng dòng, dùng luôn làm
evidence.

Ở đây chỉ giữ lại token cấp ngoài cùng và quy về vài loại block. Riêng "cấp
heading nào mang nghĩa gì" lấy từ profile (`extract.heading_roles`), nên tài liệu dùng
`###` cho bảng chỉ cần sửa JSON.
"""

from __future__ import annotations

import sys
from collections import Counter
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from ...config import CFG, PROCESSED_DIR, listdir, rel, require, resolve

# token mở của markdown-it -> loại block dùng trong hệ thống
BLOCK_TYPES = {
    "heading_open": "heading",
    "paragraph_open": "paragraph",
    "table_open": "table",
    "bullet_list_open": "list",
    "ordered_list_open": "list",
    "blockquote_open": "quote",
    "fence": "code",
    "code_block": "code",
    "html_block": "html",
}


@dataclass
class Block:
    """Một khối nội dung, chưa đọc bên trong."""

    # Không có trường `order`: thứ tự đọc ĐÃ là thứ tự của mảng. Lưu thêm một
    # bản sao chỉ tạo chỗ cho hai nguồn sự thật lệch nhau.
    id: str
    type: str                 # heading | paragraph | table | list | quote | code | html
    text: str                 # heading: tiêu đề; còn lại: markdown gốc của khối
    line_start: int           # 1-indexed, tính trên file .md
    line_end: int
    level: int | None = None  # chỉ heading
    role: str | None = None   # chỉ heading, lấy từ extract.heading_roles


@lru_cache(maxsize=1)
def _parser():
    from markdown_it import MarkdownIt

    # commonmark + bảng GFM. Không bật linkify (cần gói riêng) vì đường link
    # không ảnh hưởng tới cấu trúc.
    return MarkdownIt("commonmark").enable("table")


def split(md: str, *, heading_roles: dict[int, str] | None = None) -> list[Block]:
    """markdown -> list[Block] theo thứ tự đọc."""
    roles = heading_roles if heading_roles is not None else CFG.extract.heading_roles
    lines = md.splitlines()
    tokens = _parser().parse(md)

    blocks: list[Block] = []
    for i, tok in enumerate(tokens):
        # level 0 = khối ngoài cùng. Bỏ token con (tr, td, li...) vì chúng là
        # nội dung bên trong khối, thuộc phần việc của `extract`.
        if tok.level != 0 or tok.type not in BLOCK_TYPES or tok.map is None:
            continue

        start, end = tok.map  # nửa mở, 0-indexed
        kind = BLOCK_TYPES[tok.type]
        level = int(tok.tag[1]) if kind == "heading" and tok.tag[1:].isdigit() else None

        if kind == "heading":
            nxt = tokens[i + 1] if i + 1 < len(tokens) else None
            text = (nxt.content if nxt is not None and nxt.type == "inline" else "").strip()
        else:
            text = "\n".join(lines[start:end]).strip()

        blocks.append(Block(
            id=f"block_{len(blocks) + 1}",
            type=kind,
            text=text,
            line_start=start + 1,
            line_end=end,
            level=level,
            role=roles.get(level) if level else None,
        ))
    return blocks


def load_markdown(name: str | Path, *, base: Path = PROCESSED_DIR) -> tuple[str, str]:
    """Trả (doc_id, markdown)."""
    src = require(resolve(name, base), base)
    return src.stem, src.read_text(encoding="utf-8")


def count_roles(blocks: list[Block]) -> dict[str, int]:
    """vai trò -> số heading mang vai trò đó. Đây là số đo cấu trúc của tài liệu."""
    return Counter(b.role for b in blocks if b.type == "heading" and b.role)


def check(blocks: list[Block], *, roles: dict[int, str] | None = None) -> list[str]:
    """Trả danh sách cảnh báo. Không tự sửa.

    Cấu trúc hỏng phải lộ ra trong `warnings` của extract, trước khi link dựng
    cây cha-con từ các heading.
    """
    roles = CFG.extract.heading_roles if roles is None else roles
    warn: list[str] = []
    if not blocks:
        return ["0 block - tài liệu rỗng"]

    have = count_roles(blocks)
    for role in dict.fromkeys(roles.values()):
        if not have.get(role):
            warn.append(
                f"0 heading vai trò '{role}' - restructure() hỏng hoặc "
                "extract.heading_roles khai sai"
            )

    if orphan := {b.level for b in blocks if b.type == "heading" and b.role is None}:
        warn.append(
            f"heading cấp {sorted(orphan)} không có vai trò trong extract.heading_roles"
        )
    return warn


def report(blocks: list[Block], warnings: list[str] | None = None) -> None:
    counts = Counter(b.type for b in blocks)
    print(f"     {len(blocks)} block | " + " ".join(f"{k}={v}" for k, v in sorted(counts.items())))
    for lvl, role in sorted(CFG.extract.heading_roles.items()):
        n = sum(1 for b in blocks if b.level == lvl)
        print(f"     {'#' * lvl:<4} -> {role:<10} {n} block")
    for w in warnings if warnings is not None else check(blocks):
        print(f"     ! {w}")


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        print(f"file có sẵn trong {rel(PROCESSED_DIR)}:")
        for n in listdir(PROCESSED_DIR, "*.md"):
            print(f"  - {n}")
        return 1

    try:
        doc_id, md = load_markdown(argv[0])
    except FileNotFoundError as e:
        print(e, file=sys.stderr)
        return 1

    blocks = split(md)
    print(f"{doc_id}.md  (soi cấu trúc, không ghi file)")
    report(blocks)
    for b in blocks[:8]:
        label = f"{b.type}{f'#{b.level}' if b.level else ''}"
        first = b.text.splitlines()[0] if b.text else ""
        print(f"       {b.id:<10} {label:<12} {first[:56]}")
    print(f"     kế tiếp: python -m src.branch_sql.offline.extract.block_extract {doc_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

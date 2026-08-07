"""docs -> markdown. Bước `load` của pipeline offline.

    uv run python -m src.retrieval.parse "Mô tả bảng BĐS (NEW).docx"

Chỉ cần tên file — mặc định tìm trong `UPLOAD_DIR`, ghi .md sang `ARTIFACT_DIR`.
"""

from __future__ import annotations

import re
import sys
import unicodedata
from pathlib import Path

from langchain_core.documents import Document
from langchain_core.runnables import Runnable, RunnableLambda
from markitdown import MarkItDown

from ..config_sql import ARTIFACT_DIR, UPLOAD_DIR, listdir, rel, require, resolve

# ---- khôi phục cấp bậc tiêu đề -------------------------------------------
# Số thứ tự là bắt buộc: nó phân biệt dòng tên bảng với dòng ghi chú cũng in đậm.
TABLE_HEADING = re.compile(r"^\*\s+\d+\.\s+\*\*Bảng\s+(?P<name>.+?)\*\*\s*$")
TOC_LINK = re.compile(r"^\[.*\]\(#_heading=[^)]*\)\s*$")
SEPARATOR = re.compile(r"^[-*_=]{10,}\s*$")
BULLET = re.compile(r"^\*\s+")
ESCAPED = re.compile(r"\\([_*\[\]()#+\-.!`])")

# ---- làm sạch -------------------------------------------------------------
INVISIBLE = re.compile(r"[\u200b-\u200f\u202a-\u202e\u2060-\u2064\ufeff\u00ad]")
HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
HTML_TAG = re.compile(r"<[^>]{1,200}>")
INJECTION = re.compile(
    r"(?im)^\s*(ignore\s+(all\s+)?previous|disregard\s+the\s+above|"
    r"bỏ qua (mọi )?hướng dẫn|system\s*:|assistant\s*:)\s*.*$"
)
# Header bảng gõ sai trong tài liệu nguồn; để nguyên thì "Cột2" thành token rác
# trong cả embedding lẫn BM25.
BAD_HEADER = re.compile(r"(?<=\|\s\*\*)Cột\d+(?=\*\*\s\|)")

TRAILING_WS = re.compile(r"[ \t]+$", re.MULTILINE)
MANY_SPACES = re.compile(r"(?<=\S)[ \t]{2,}")
MANY_BLANKS = re.compile(r"\n{3,}")


def slugify(name: str) -> str:
    """'Mô tả bảng BĐS (NEW)' -> 'mo_ta_bang_bds_new'. Dùng làm doc_id."""
    s = unicodedata.normalize("NFD", name)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = s.replace("đ", "d").replace("Đ", "D").lower()
    return re.sub(r"[^a-z0-9]+", "_", s).strip("_")


def restructure(raw: str) -> str:
    """markitdown thô -> markdown có `#` nhóm / `##` bảng, bỏ mục lục.

    Tên bảng trong docx dùng style `normal` chứ không phải Heading, nên
    markitdown xuất ra bullet in đậm. Không nâng lên `##` thì splitter chỉ cắt
    được theo nhóm nghiệp vụ.
    """
    raw = ESCAPED.sub(r"\1", raw)

    out: list[str] = []
    in_toc = True  # mọi thứ trước heading đầu tiên là mục lục

    for line in raw.splitlines():
        s = line.strip()
        if in_toc:
            if s.startswith("# "):
                in_toc = False
            else:
                continue
        if TOC_LINK.match(s) or SEPARATOR.match(s):
            continue
        if m := TABLE_HEADING.match(s):
            out += ["", f"## Bảng {m['name'].strip()}", ""]
            continue
        if s.startswith("# "):
            out += ["", s, ""]
            continue
        out.append(BULLET.sub("", line) if BULLET.match(s) else line)

    return "\n".join(out)


def sanitize(md: str) -> tuple[str, list[str]]:
    """Chuẩn hoá và làm sạch. Trả (markdown, cảnh báo)."""
    warn: list[str] = []

    # Tiếng Việt có dạng tổ hợp dấu; NFD làm lệch token lẫn content_hash.
    fixed = unicodedata.normalize("NFC", md)
    if fixed != md:
        warn.append("unicode không ở dạng NFC - đã chuẩn hoá")
    md = fixed

    if INVISIBLE.search(md):
        warn.append(f"bỏ {len(INVISIBLE.findall(md))} ký tự vô hình")
        md = INVISIBLE.sub("", md)
    if HTML_COMMENT.search(md) or HTML_TAG.search(md):
        warn.append("bỏ thẻ/comment HTML còn sót")
        md = HTML_TAG.sub("", HTML_COMMENT.sub("", md))
    if hits := INJECTION.findall(md):
        warn.append(f"NGHI VẤN prompt injection: {len(hits)} dòng - đã bỏ")
        md = INJECTION.sub("", md)

    if n := len(BAD_HEADER.findall(md)):
        warn.append(f"header bảng gõ sai ở {n} chỗ - đã đổi thành 'Tên cột'")
        md = BAD_HEADER.sub("Tên cột", md)

    md = MANY_BLANKS.sub("\n\n", MANY_SPACES.sub(" ", TRAILING_WS.sub("", md)))
    return md.strip() + "\n", warn


def parse(name: str | Path, *, base: Path = UPLOAD_DIR) -> Document:
    """Tên file -> Document chứa markdown đã dựng cấu trúc và làm sạch."""
    src = require(resolve(name, base), base)
    md, warn = sanitize(restructure(MarkItDown().convert(str(src)).text_content))

    n_h2 = sum(1 for line in md.splitlines() if line.startswith("## "))
    if n_h2 == 0:
        warn.append("KHÔNG có heading `##` - chunking sẽ cắt sai, kiểm tra lại")
    if len(md.strip()) < 50:
        raise ValueError(f"{src.name}: markdown gần như rỗng - file scan chưa OCR?")

    return Document(
        page_content=md,
        metadata={
            "doc_id": slugify(src.stem),
            "title": src.stem,
            "source_name": src.name,
            "n_sections": sum(1 for line in md.splitlines() if line.startswith("# ")),
            "n_tables": n_h2,
            "warnings": warn,
        },
    )


def write_markdown(doc: Document, *, out_dir: Path = ARTIFACT_DIR) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    dst = out_dir / f"{doc.metadata['doc_id']}.md"
    dst.write_text(doc.page_content, encoding="utf-8")
    return dst


def as_runnable(*, base: Path = UPLOAD_DIR) -> Runnable[str, Document]:
    """Bước `parse` để nối vào LCEL chain."""
    return RunnableLambda(lambda name: parse(name, base=base), name="parse")


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        print(f"file có sẵn trong {rel(UPLOAD_DIR)}:")
        for n in listdir(UPLOAD_DIR):
            print(f"  - {n}")
        return 1

    try:
        doc = parse(argv[0])
    except (FileNotFoundError, ValueError) as e:
        print(e, file=sys.stderr)
        return 1

    dst = write_markdown(doc)
    m = doc.metadata
    print(f"{m['source_name']}\n  -> {rel(dst)}")
    print(f"     {len(doc.page_content):,} ký tự | {m['n_sections']} nhóm (#) | {m['n_tables']} bảng (##)")
    for w in m["warnings"]:
        print(f"     ! {w}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

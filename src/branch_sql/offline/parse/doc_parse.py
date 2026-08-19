"""tài liệu -> markdown. Nửa đầu của chặng `parse`.

    uv run python -m src.branch_sql.offline.parse.doc_parse "Mô tả bảng BĐS (NEW).docx"

Chỉ cần tên file — mặc định tìm trong `RAW_DIR`, ghi .md sang `PROCESSED_DIR`.

Chọn loader theo đuôi file, rồi làm sạch bằng cùng một bộ luật cho mọi định dạng:

    .pdf         pdf_parse    docling, có mô hình layout   ~75 giây
    còn lại      docx_parse   markitdown                   < 1 giây

Chỉ lo tới *văn bản*: chuyển định dạng, khôi phục cấp bậc tiêu đề, làm sạch. Việc
đếm xem tài liệu có bao nhiêu bảng, cấu trúc đúng hay hỏng là của `blocks.py` —
nó có parser CommonMark thật nên đếm đúng cả những ca `#` nằm trong khối code.
"""

from __future__ import annotations

import re
import sys
import unicodedata
from pathlib import Path

from langchain_core.documents import Document

from ...config import CFG, DOC_SUFFIXES, PROCESSED_DIR, RAW_DIR, listdir, rel, require, resolve
from . import docx_parse

# ---- làm sạch, áp cho mọi loader -----------------------------------------
INVISIBLE = re.compile(r"[​-‏‪-‮⁠-⁤﻿­]")
HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
# Danh sách trắng tên thẻ, KHÔNG phải `[A-Za-z][^>]*`. Tài liệu schema viết
# placeholder kiểu `<NEW>`, `<PENDING>`, `<ten_user>` — luật cũ xoá sạch chúng và
# chỉ để lại một dòng cảnh báo đếm số, không cách nào truy ra đã mất gì.
_TAGS = (
    r"a|abbr|b|blockquote|br|caption|code|col|colgroup|div|em|figcaption|figure|"
    r"h[1-6]|head|hr|html|i|img|li|meta|ol|p|pre|s|script|small|span|strong|style|"
    r"sub|sup|table|tbody|td|tfoot|th|thead|tr|u|ul|font|[ovw]:[a-z]+"
)
HTML_TAG = re.compile(rf"</?(?:{_TAGS})(?:\s[^>]{{0,200}})?/?>", re.IGNORECASE)
# Dải gạch ngang ngăn mục. markitdown và docling đều sinh ra, nên nó ở đây chứ
# không nằm riêng trong một loader.
SEPARATOR = re.compile(r"(?m)^[-*_=]{10,}[ \t]*$")
# Chỉ CẢNH BÁO, không xoá. Đây là KB do người vận hành kiểm soát; xoá nhầm một
# dòng "System: ERP quản lý kho" là mất dữ liệu thật, còn injection thật thì nằm
# trong ô bảng chứ không nằm đầu dòng. Chặn thật sự là việc của lúc lắp prompt.
INJECTION = re.compile(
    r"(?im)^\s*(ignore\s+(all\s+)?previous|disregard\s+the\s+above|"
    r"bỏ qua (mọi )?hướng dẫn|system\s*:|assistant\s*:)\s*.*$"
)

TRAILING_WS = re.compile(r"[ \t]+$", re.MULTILINE)
MANY_SPACES = re.compile(r"(?<=\S)[ \t]{2,}")
MANY_BLANKS = re.compile(r"\n{3,}")


def slugify(name: str) -> str:
    """'Mô tả bảng BĐS (NEW)' -> 'mo_ta_bang_bds_new'."""
    s = unicodedata.normalize("NFD", name)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = s.replace("đ", "d").replace("Đ", "D").lower()
    return re.sub(r"[^a-z0-9]+", "_", s).strip("_")


def doc_id_of(src: Path) -> str:
    """'Mô tả bảng BĐS (NEW).docx' -> 'mo_ta_bang_bds_new__docx'.

    Đuôi nguồn nằm TRONG doc_id vì mọi artifact đều đặt tên theo nó. Thiếu nó
    thì bản .docx và bản .pdf của cùng tài liệu ghi đè lên nhau, im lặng.
    """
    return f"{slugify(src.stem)}__{src.suffix.lstrip('.').lower()}"


def to_markdown(src: Path) -> str:
    """Chọn loader theo đuôi file. docling nặng nên chỉ import khi gặp .pdf.

    Đuôi lạ phải chết ở đây với thông báo rõ ràng; thả xuống loader thì lỗi hiện
    ra từ trong thư viện và không nói được là định dạng không được khai báo.
    """
    if src.suffix.lower() not in DOC_SUFFIXES:
        raise ValueError(
            f"{src.name}: đuôi '{src.suffix}' không có trong parse.suffixes "
            f"({', '.join(sorted(DOC_SUFFIXES))})"
        )
    if src.suffix.lower() == ".pdf":
        from . import pdf_parse

        return pdf_parse.to_markdown(src)
    return docx_parse.to_markdown(src)


def sanitize(md: str, *, replacements=None) -> tuple[str, list[str]]:
    """Chuẩn hoá và làm sạch. Trả (markdown, cảnh báo)."""
    warn: list[str] = []
    replacements = CFG.parse.replacements if replacements is None else replacements

    # Tiếng Việt có dạng tổ hợp dấu; NFD làm lệch token lẫn content_hash.
    fixed = unicodedata.normalize("NFC", md)
    if fixed != md:
        warn.append("unicode không ở dạng NFC - đã chuẩn hoá")
    md = fixed

    if INVISIBLE.search(md):
        warn.append(f"bỏ {len(INVISIBLE.findall(md))} ký tự vô hình")
        md = INVISIBLE.sub("", md)

    # Liệt kê đúng cái đã bỏ. Đếm số thì không audit được, mà đây là thao tác
    # DUY NHẤT trong sanitize có thể ăn mất nội dung thật.
    tags = sorted({m.group() for m in HTML_TAG.finditer(md)})
    if tags or HTML_COMMENT.search(md):
        listed = ": " + ", ".join(tags[:5]) + ("..." if len(tags) > 5 else "") if tags else ""
        warn.append(f"bỏ thẻ/comment HTML còn sót{listed}")
        md = HTML_TAG.sub("", HTML_COMMENT.sub("", md))
    if n := len(SEPARATOR.findall(md)):
        warn.append(f"bỏ {n} dải gạch ngang ngăn mục")
        md = SEPARATOR.sub("", md)

    # Cảnh báo, KHÔNG xoá - xem chú thích ở INJECTION.
    if hits := INJECTION.findall(md):
        warn.append(
            f"NGHI VẤN prompt injection: {len(hits)} dòng - GIỮ NGUYÊN, soi lại bằng mắt"
        )

    # Lỗi gõ riêng của bộ tài liệu, khai ở `parse.replacements` trong profile.
    for r in replacements:
        md, n = re.subn(r.pattern, r.replace, md)
        if n:
            warn.append(f"sửa {n} chỗ khớp /{r.pattern}/ -> '{r.replace}'")

    md = MANY_BLANKS.sub("\n\n", MANY_SPACES.sub(" ", TRAILING_WS.sub("", md)))
    return md.strip() + "\n", warn


def unique_doc_id(src: Path) -> str:
    """`doc_id` của file, sau khi chắc chắn không file nào khác cùng thư mục
    sinh ra đúng `doc_id` đó.

    `slugify` bỏ dấu và gộp mọi ký tự không phải chữ-số thành `_`, nên nó nén
    rất mạnh: "Mô-tả bảng BĐS [NEW]" và "Mô tả bảng BĐS (NEW)" ra cùng một chuỗi.
    Đụng nhau mà không chặn ở đây thì hai tài liệu ghi đè artifact của nhau và
    không có dấu vết nào.
    """
    doc_id = doc_id_of(src)
    clash = sorted(
        p.name for p in src.parent.glob("*")
        if p.is_file() and p.resolve() != src.resolve() and doc_id_of(p) == doc_id
    )
    if clash:
        raise ValueError(
            f"{src.name}: doc_id '{doc_id}' trùng với {', '.join(clash)}.\n"
            f"Artifact đặt tên theo doc_id nên chúng sẽ ghi đè nhau - đổi tên file nguồn."
        )
    return doc_id


def parse(name: str | Path, *, base: Path = RAW_DIR) -> Document:
    """Tên file -> Document chứa markdown đã dựng cấu trúc và làm sạch."""
    src = require(resolve(name, base), base)
    doc_id = unique_doc_id(src)
    md, warn = sanitize(to_markdown(src))

    if len(md) < 50:
        raise ValueError(f"{src.name}: markdown gần như rỗng - file scan chưa OCR?")

    return Document(
        page_content=md,
        metadata={
            "doc_id": doc_id,
            "title": src.stem,
            "source_name": src.name,
            "warnings": warn,
        },
    )


def write_markdown(doc: Document, *, out_dir: Path = PROCESSED_DIR) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    dst = out_dir / f"{doc.metadata['doc_id']}.md"
    dst.write_text(doc.page_content, encoding="utf-8")
    return dst


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        print(f"file có sẵn trong {rel(RAW_DIR)}:")
        for n in listdir(RAW_DIR):
            print(f"  - {n}")
        return 1

    try:
        doc = parse(argv[0])
    except (FileNotFoundError, ImportError, ValueError) as e:
        print(e, file=sys.stderr)
        return 1

    dst = write_markdown(doc)
    print(f"{doc.metadata['source_name']}\n  -> {rel(dst)}")
    print(f"     {len(doc.page_content):,} ký tự")
    for w in doc.metadata["warnings"]:
        print(f"     ! {w}")
    print(f"     kế tiếp: python -m src.branch_sql.offline.extract.block_extract "
          f"{doc.metadata['doc_id']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

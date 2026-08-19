"""docx (và các định dạng markitdown đọc được) -> markdown có heading.

Một trong hai loader của chặng `parse`. Phần dùng chung — làm sạch, đặt doc_id,
ghi file — nằm ở `doc_parse.py`; ở đây chỉ có việc riêng của markitdown.

markitdown đọc .docx qua mammoth, giữ nguyên bảng thành bảng GFM nên không cần
mô hình layout như bản PDF. Chạy dưới một giây.
"""

from __future__ import annotations

import re
from pathlib import Path

from markitdown import MarkItDown

from ...config import CFG

# ---- khôi phục cấp bậc tiêu đề -------------------------------------------
# Luật nhận diện dòng tên bảng nằm ở `parse.table_heading` trong profile: nó là
# quy ước trình bày của MỘT bộ tài liệu, không phải luật của markdown.
TOC_LINK = re.compile(r"^\[.*\]\(#_heading=[^)]*\)\s*$")
BULLET = re.compile(r"^\*\s+")
ESCAPED = re.compile(r"\\([_*\[\]()#+\-.!`])")


def restructure(raw: str, *, table_heading: re.Pattern | None = None) -> str:
    """markitdown thô -> markdown có `#` nhóm / `##` bảng, bỏ mục lục.

    Tên bảng trong docx dùng style `normal` chứ không phải Heading, nên
    markitdown xuất ra bullet in đậm. Không nâng lên `##` thì splitter chỉ cắt
    được theo nhóm nghiệp vụ.

    `table_heading` phải có nhóm bắt tên là `name`; phần tên đi thẳng vào tiêu
    đề nên tiền tố ("Bảng", "Table"...) do profile quyết định, không do code.
    """
    heading_re = CFG.parse.table_heading_re if table_heading is None else table_heading
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
        if TOC_LINK.match(s):
            continue
        if heading_re is not None and (m := heading_re.match(s)):
            out += ["", f"## {m['name'].strip()}", ""]
            continue
        if s.startswith("# "):
            out += ["", s, ""]
            continue
        out.append(BULLET.sub("", line) if BULLET.match(s) else line)

    return "\n".join(out)


def to_markdown(src: Path) -> str:
    """File -> markdown đã dựng cấu trúc, chưa làm sạch."""
    return restructure(MarkItDown().convert(str(src)).text_content)

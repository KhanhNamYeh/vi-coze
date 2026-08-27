"""DOCX -> Markdown; chuẩn hóa bullet tiêu đề bản ghi thành H2."""

import re
from pathlib import Path


NUMBERED_BOLD_HEADING = re.compile(
    r"^\s*[*+-]\s+\d+(?:\.\d+)*\.\s+\*\*(.+?)\*\*\s*$"
)


def _normalize_record_headings(markdown: str, heading_level: int) -> str:
    """Dùng cấu trúc Markdown, không phụ thuộc tên bảng cụ thể."""
    lines = []
    for line in markdown.splitlines():
        match = NUMBERED_BOLD_HEADING.match(line)
        lines.append(f"{'#' * heading_level} {match.group(1).strip()}" if match else line)
    return "\n".join(lines)


def to_markdown(source: str | Path, *, record_heading_level: int = 2) -> str:
    from markitdown import MarkItDown

    path = Path(source)
    markdown = _normalize_record_headings(
        MarkItDown().convert(str(path)).text_content,
        record_heading_level,
    )
    if not markdown.strip():
        raise ValueError(f"{path.name}: MarkItDown trả về Markdown rỗng")
    return markdown

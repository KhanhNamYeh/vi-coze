"""PDF -> Markdown bằng output nguyên bản của Docling."""

from pathlib import Path


def to_markdown(source: str | Path) -> str:
    try:
        from docling.document_converter import DocumentConverter
    except ImportError as error:
        raise ImportError("Đọc PDF cần dependency `docling` (uv sync --extra pdf)") from error

    path = Path(source)
    markdown = DocumentConverter().convert(str(path)).document.export_to_markdown()
    if not markdown.strip():
        raise ValueError(f"{path.name}: Docling trả về Markdown rỗng")
    return markdown

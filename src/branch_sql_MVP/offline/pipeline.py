"""Điều phối: tài liệu -> preprocess -> extract -> link -> chunk -> embed -> index."""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path

from ..settings import Settings, load_settings
from ..preprocess import docx_parse, pdf_parse, xlsx_parse
from . import chunk, embed, extract, graph, index, link


def _slug(value: str) -> str:
    value = unicodedata.normalize("NFD", value)
    value = "".join(char for char in value if unicodedata.category(char) != "Mn")
    return re.sub(r"[^a-z0-9]+", "_", value.lower().replace("đ", "d")).strip("_")


def resolve_source(source: str | Path, settings: Settings) -> Path:
    path = Path(source)
    if not path.is_absolute():
        path = settings.path(settings.paths.raw) / path
    path = path.resolve()
    if not path.is_file():
        raise FileNotFoundError(path)
    return path


def preprocess(source: str | Path, *, settings: Settings | None = None) -> dict:
    app = settings or load_settings()
    path = resolve_source(source, app)
    suffix = path.suffix.lower()
    if suffix == ".md":
        markdown = path.read_text(encoding="utf-8")
    elif suffix == ".docx":
        markdown = docx_parse.to_markdown(
            path,
            record_heading_level=app.preprocess.record_heading_level,
        )
    elif suffix == ".pdf":
        markdown = pdf_parse.to_markdown(path)
    elif suffix == ".xlsx":
        markdown = xlsx_parse.to_markdown(path, app.preprocess)
    else:
        raise ValueError(f"chưa hỗ trợ định dạng '{suffix}'")
    if not markdown.strip():
        raise ValueError(f"{path.name}: Markdown rỗng")

    doc_id = f"{_slug(path.stem)}__{suffix.removeprefix('.')}"
    output = app.path(app.paths.markdown) / f"{doc_id}.md"
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists() and not app.preprocess.overwrite:
        raise FileExistsError(f"{output} đã tồn tại và preprocess.overwrite=false")
    output.write_text(markdown.rstrip() + "\n", encoding="utf-8")
    return {"doc_id": doc_id, "source": str(path), "path": str(output)}


def run(
    source: str | Path,
    *,
    kind: str,
    knowledge_id: str | None = None,
    recreate: bool | None = None,
    graph_provider: str | None = None,
    graph_model: str | None = None,
    graph_api_key: str | None = None,
    settings: Settings | None = None,
) -> dict:
    app = settings or load_settings()
    parsed = preprocess(source, settings=app)
    extracted = extract.run(parsed["path"], settings=app)
    linked = link.run(parsed["doc_id"], settings=app)
    chunked = chunk.run(parsed["doc_id"], settings=app)
    graphed = graph.run(
        parsed["doc_id"],
        kind=kind,
        provider=graph_provider,
        model=graph_model,
        api_key=graph_api_key,
        settings=app,
    )
    embedded = embed.run(parsed["doc_id"], settings=app)
    indexed = index.run(
        parsed["doc_id"],
        kind=kind,
        knowledge_id=knowledge_id,
        recreate=recreate,
        settings=app,
    )
    return {
        "preprocess": parsed,
        "extract": {"elements": len(extracted["elements"]), "path": extracted["path"]},
        "link": {"elements": len(linked["elements"]), "path": linked["path"]},
        "chunk": chunked,
        "graph": graphed,
        "embed": embedded,
        "index": indexed,
    }

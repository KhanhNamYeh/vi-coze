"""Markdown -> đúng ba loại phần tử: heading, table, text."""

from __future__ import annotations

import json
from pathlib import Path

from markdown_it import MarkdownIt

from ..settings import Settings, load_settings


def _parser() -> MarkdownIt:
    return MarkdownIt("commonmark").enable("table")


def extract(markdown: str) -> list[dict]:
    lines = markdown.splitlines()
    tokens = _parser().parse(markdown)
    elements: list[dict] = []
    consumed_until = -1

    for index, token in enumerate(tokens):
        if token.level != 0 or token.map is None:
            continue
        start, end = token.map
        if start < consumed_until:
            continue

        if token.type == "heading_open":
            inline = tokens[index + 1] if index + 1 < len(tokens) else None
            element = {
                "type": "heading",
                "text": (inline.content if inline else "").strip(),
                "level": int(token.tag.removeprefix("h")),
            }
        elif token.type == "table_open":
            element = {"type": "table", "text": "\n".join(lines[start:end]).strip()}
        else:
            element = {"type": "text", "text": "\n".join(lines[start:end]).strip()}

        if element["text"]:
            element["id"] = f"el_{len(elements) + 1}"
            elements.append(element)
        consumed_until = end

    if not elements:
        raise ValueError("extract không tạo được heading, table hoặc text nào")
    return elements


def run(markdown_path: str | Path, *, settings: Settings | None = None) -> dict:
    cfg = settings or load_settings()
    source = Path(markdown_path)
    result = {"doc_id": source.stem, "source": source.name, "elements": extract(source.read_text(encoding="utf-8"))}
    output = cfg.path(cfg.paths.artifacts) / f"{source.stem}.extract.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {**result, "path": str(output)}


def load(doc_id: str, *, settings: Settings | None = None) -> dict:
    cfg = settings or load_settings()
    path = cfg.path(cfg.paths.artifacts) / f"{doc_id}.extract.json"
    if not path.exists():
        raise FileNotFoundError(f"chưa có {path.name}; chạy extract trước")
    return json.loads(path.read_text(encoding="utf-8"))

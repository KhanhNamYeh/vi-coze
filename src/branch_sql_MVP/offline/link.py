"""Gắn duy nhất quan hệ parent_id theo cây heading."""

from __future__ import annotations

import json
from pathlib import Path

from ..settings import Settings, load_settings
from .extract import load as load_extract


def link(elements: list[dict]) -> list[dict]:
    linked: list[dict] = []
    headings: list[dict] = []
    for source in elements:
        element = dict(source)
        if element["type"] == "heading":
            while headings and headings[-1]["level"] >= element["level"]:
                headings.pop()
        element["parent_id"] = headings[-1]["id"] if headings else None
        linked.append(element)
        if element["type"] == "heading":
            headings.append(element)
    return linked


def run(doc_id: str, *, settings: Settings | None = None) -> dict:
    cfg = settings or load_settings()
    source = load_extract(doc_id, settings=cfg)
    result = {**source, "elements": link(source["elements"])}
    result.pop("path", None)
    output = cfg.path(cfg.paths.artifacts) / f"{doc_id}.linked.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {**result, "path": str(output)}


def load(doc_id: str, *, settings: Settings | None = None) -> dict:
    cfg = settings or load_settings()
    path = cfg.path(cfg.paths.artifacts) / f"{doc_id}.linked.json"
    if not path.exists():
        raise FileNotFoundError(f"chưa có {path.name}; chạy link trước")
    return json.loads(path.read_text(encoding="utf-8"))

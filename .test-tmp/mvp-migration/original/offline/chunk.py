"""Linked blocks -> parent/child chunks; chỉ có một luồng parent-child."""

from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from pathlib import Path

from ..settings import ChunkSettings, Settings, load_settings
from .link import load as load_linked


@lru_cache(maxsize=4)
def _tokenizer(model: str):
    from transformers import AutoTokenizer

    return AutoTokenizer.from_pretrained(model)


def measure(text: str, cfg: ChunkSettings, dense_model: str = "") -> int:
    if cfg.unit == "character":
        return len(text)
    model = cfg.tokenizer_model or dense_model
    if not model:
        raise ValueError("chunk cần tokenizer_model hoặc embedding.dense_model")
    return len(_tokenizer(model).encode(text, add_special_tokens=True))


def _cut(text: str, limit: int, cfg: ChunkSettings, dense_model: str) -> str:
    if cfg.unit == "character":
        return text[:limit]
    tokenizer = _tokenizer(cfg.tokenizer_model or dense_model)
    return tokenizer.decode(tokenizer.encode(text, add_special_tokens=False)[:limit])


def _tail(text: str, size: int, cfg: ChunkSettings, dense_model: str) -> str:
    if size <= 0:
        return ""
    if cfg.unit == "character":
        return text[-size:]
    tokenizer = _tokenizer(cfg.tokenizer_model or dense_model)
    ids = tokenizer.encode(text, add_special_tokens=False)
    return tokenizer.decode(ids[-size:])


def split_text(text: str, limit: int, cfg: ChunkSettings, dense_model: str) -> list[str]:
    """Cắt đệ quy theo separator rồi thêm overlap giữa các mảnh."""
    text = text.strip()
    if not text:
        return []
    if measure(text, cfg, dense_model) <= limit:
        return [text]
    if cfg.on_overflow == "truncate":
        return [_cut(text, limit, cfg, dense_model).strip()]

    def atomic(value: str, separators: list[str]) -> list[str]:
        if measure(value, cfg, dense_model) <= limit:
            return [value.strip()]
        if not separators or separators[0] == "":
            step = max(1, limit - cfg.child_overlap)
            if cfg.unit == "character":
                return [value[i : i + limit].strip() for i in range(0, len(value), step)]
            tokenizer = _tokenizer(cfg.tokenizer_model or dense_model)
            ids = tokenizer.encode(value, add_special_tokens=False)
            return [tokenizer.decode(ids[i : i + limit]).strip() for i in range(0, len(ids), step)]
        separator, rest = separators[0], separators[1:]
        pieces = [piece for piece in value.split(separator) if piece.strip()]
        if len(pieces) == 1:
            return atomic(value, rest)
        output: list[str] = []
        for piece in pieces:
            output.extend(atomic(piece, rest))
        return output

    pieces = atomic(text, cfg.separators)
    output: list[str] = []
    current = ""
    for piece in pieces:
        candidate = f"{current}\n{piece}".strip()
        if current and measure(candidate, cfg, dense_model) > limit:
            output.append(current)
            overlap = _tail(current, cfg.child_overlap, cfg, dense_model)
            current = f"{overlap}\n{piece}".strip()
            if measure(current, cfg, dense_model) > limit:
                current = piece
        else:
            current = candidate
    if current:
        output.append(current)
    return [part for part in output if part]


def _render(element: dict) -> str:
    if element["type"] == "heading":
        return f"{'#' * element['level']} {element['text']}"
    return element["text"]


def _units(elements: list[dict], heading_level: int) -> list[list[dict]]:
    levels = sorted({
        element["level"]
        for element in elements
        if element["type"] == "heading" and element.get("level")
    })
    if heading_level not in levels:
        available = ", ".join(f"H{level}" for level in levels) or "không có heading"
        raise ValueError(f"chunk yêu cầu H{heading_level}, tài liệu chỉ có: {available}")
    groups: list[list[dict]] = []
    current: list[dict] = []
    found_boundary = False
    for element in elements:
        level = element.get("level") if element["type"] == "heading" else None
        if level is not None and level < heading_level:
            if current and any(item["type"] != "heading" for item in current):
                groups.append(current)
            current = []
            found_boundary = False
            continue
        boundary = level == heading_level
        if boundary:
            found_boundary = True
            if current and any(item["type"] != "heading" for item in current):
                groups.append(current)
            current = [element]
        elif found_boundary:
            current.append(element)
    if current and any(item["type"] != "heading" for item in current):
        groups.append(current)
    return groups


def _breadcrumb(element: dict, by_id: dict[str, dict]) -> str:
    names: list[str] = []
    current: dict | None = element
    while current:
        if current.get("type") == "heading":
            names.append(current["text"])
        current = by_id.get(current.get("parent_id"))
    return " > ".join(reversed(names))


def _table_parts(markdown: str, cfg: ChunkSettings) -> list[str]:
    lines = [line for line in markdown.splitlines() if line.strip()]
    if len(lines) < 3:
        return [markdown]
    header, separator, rows = lines[0], lines[1], lines[2:]
    step = max(1, cfg.table_rows - cfg.table_overlap_rows)
    output = []
    for start in range(0, len(rows), step):
        body = rows[start : start + cfg.table_rows]
        prefix = [header, separator] if cfg.repeat_table_header or start == 0 else []
        output.append("\n".join(prefix + body))
        if start + cfg.table_rows >= len(rows):
            break
    return output


def _id(*values: str) -> str:
    return hashlib.sha256("\0".join(values).encode("utf-8")).hexdigest()[:24]


def build(ir: dict, cfg: ChunkSettings, dense_model: str) -> tuple[list[dict], list[dict]]:
    elements = ir["elements"]
    if not elements:
        raise ValueError("chunk nhận danh sách element rỗng")
    by_id = {element["id"]: element for element in elements}
    parents: list[dict] = []
    children: list[dict] = []

    for unit_number, unit in enumerate(_units(elements, cfg.heading_level), 1):
        full_text = "\n\n".join(_render(element) for element in unit).strip()
        if not full_text:
            continue
        parent_text = _cut(full_text, cfg.parent_max, cfg, dense_model).strip()
        parent_id = _id(ir["doc_id"], "parent", str(unit_number), parent_text)
        first = unit[0]
        section_id = first["text"]
        crumb = _breadcrumb(first, by_id) if cfg.breadcrumb else ""
        context = crumb.strip()
        reserve = measure(context + "\n", cfg, dense_model) if context else 0
        body_limit = max(1, cfg.child_max - reserve)
        raw_parts: list[tuple[str, str]] = []
        prose: list[str] = []

        def flush_prose() -> None:
            if not prose:
                return
            raw = "\n\n".join(prose)
            raw_parts.extend((part, "text") for part in split_text(raw, body_limit, cfg, dense_model))
            prose.clear()

        for position, element in enumerate(unit):
            # H2 hiện tại đã nằm trong breadcrumb; không chèn lại vào body.
            if position == 0 and element["type"] == "heading":
                continue
            if element["type"] == "table":
                flush_prose()
                for table in _table_parts(element["text"], cfg):
                    raw_parts.extend((part, "table") for part in split_text(table, body_limit, cfg, dense_model))
            else:
                prose.append(_render(element))
        flush_prose()

        made: list[dict] = []
        for body, kind in raw_parts:
            text = f"{context}\n{body}".strip() if context else body.strip()
            if not text:
                continue
            if measure(text, cfg, dense_model) > cfg.child_max:
                text = _cut(text, cfg.child_max, cfg, dense_model).strip()
            made.append({
                "id": _id(ir["doc_id"], parent_id, str(len(made) + 1), text),
                "parent_id": parent_id,
                "text": text,
                "type": kind,
                "source": ir["source"],
                "section_id": section_id,
            })

        if cfg.on_underflow == "drop":
            made = [item for item in made if measure(item["text"], cfg, dense_model) >= cfg.child_min]
        elif cfg.on_underflow == "merge":
            merged: list[dict] = []
            for item in made:
                if merged and measure(item["text"], cfg, dense_model) < cfg.child_min:
                    combined = f"{merged[-1]['text']}\n{item['text']}"
                    if measure(combined, cfg, dense_model) <= cfg.child_max:
                        merged[-1] = {**merged[-1], "text": combined, "id": _id(ir["doc_id"], parent_id, combined)}
                        continue
                merged.append(item)
            index = 0
            while index < len(merged):
                if measure(merged[index]["text"], cfg, dense_model) >= cfg.child_min:
                    index += 1
                    continue
                if index + 1 < len(merged):
                    combined = f"{merged[index]['text']}\n{merged[index + 1]['text']}"
                    if measure(combined, cfg, dense_model) <= cfg.child_max:
                        following = merged[index + 1]
                        kind = merged[index]["type"] if merged[index]["type"] == following["type"] else "text"
                        merged[index + 1] = {
                            **following,
                            "id": _id(ir["doc_id"], parent_id, combined),
                            "text": combined,
                            "type": kind,
                        }
                        merged.pop(index)
                        continue
                # Không thể ghép mà vẫn tôn trọng child_max: bỏ chunk thiếu nội dung.
                merged.pop(index)
            made = merged
        if not made:
            continue
        parents.append({
            "id": parent_id,
            "text": parent_text,
            "source": ir["source"],
            "section_id": section_id,
        })
        children.extend(made)

    if not children:
        raise ValueError("chunk tạo ra 0 child chunk")
    empty = [item["id"] for item in children if not item["text"].strip()]
    oversized = [item["id"] for item in children if measure(item["text"], cfg, dense_model) > cfg.child_max]
    underfilled = [
        item["id"]
        for item in children
        if cfg.on_underflow != "keep" and measure(item["text"], cfg, dense_model) < cfg.child_min
    ]
    orphaned = [item["id"] for item in children if item["parent_id"] not in {p["id"] for p in parents}]
    if empty or oversized or underfilled or orphaned:
        raise ValueError(
            "chunk không hợp lệ: "
            f"empty={len(empty)}, oversized={len(oversized)}, "
            f"underfilled={len(underfilled)}, orphaned={len(orphaned)}"
        )
    return children, parents


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")


def run(doc_id: str, *, settings: Settings | None = None) -> dict:
    app = settings or load_settings()
    ir = load_linked(doc_id, settings=app)
    children, parents = build(ir, app.chunk, app.embedding.dense_model)
    base = app.path(app.paths.artifacts)
    base.mkdir(parents=True, exist_ok=True)
    child_path, parent_path = base / f"{doc_id}.chunks.jsonl", base / f"{doc_id}.parents.jsonl"
    _write_jsonl(child_path, children)
    _write_jsonl(parent_path, parents)
    return {"doc_id": doc_id, "chunks": len(children), "parents": len(parents), "path": str(child_path), "parent_path": str(parent_path)}


def load_chunks(doc_id: str, *, settings: Settings | None = None) -> list[dict]:
    app = settings or load_settings()
    path = app.path(app.paths.artifacts) / f"{doc_id}.chunks.jsonl"
    if not path.exists():
        raise FileNotFoundError(f"chưa có {path.name}; chạy chunk trước")
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not rows:
        raise ValueError(f"{path.name} không có chunk")
    return rows

"""Xây event–entity artifact riêng cho relational context kiểu SAG."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any


def _id(*values: str) -> str:
    return hashlib.sha256("\0".join(values).encode("utf-8")).hexdigest()[:24]


def _business_sections(text: str) -> list[tuple[str, str]]:
    sections: list[tuple[str, str]] = []
    heading = "Tài liệu nghiệp vụ"
    body: list[str] = []
    for line in text.splitlines():
        if line.startswith(("## ", "### ")):
            if body and " ".join(body).strip():
                sections.append((heading, "\n".join(body).strip()))
            heading = line.lstrip("# ").strip()
            body = []
        elif line.strip():
            body.append(line)
    if body and " ".join(body).strip():
        sections.append((heading, "\n".join(body).strip()))
    return sections


def _bounded_blocks(text: str, max_characters: int = 1200) -> list[str]:
    blocks: list[str] = []
    current: list[str] = []
    size = 0
    for line in text.splitlines():
        pieces = [line[start : start + max_characters] for start in range(0, len(line), max_characters)] or [""]
        for piece in pieces:
            extra = len(piece) + (1 if current else 0)
            if current and size + extra > max_characters:
                blocks.append("\n".join(current))
                current = []
                size = 0
            if piece:
                current.append(piece)
                size += len(piece) + (1 if len(current) > 1 else 0)
    if current:
        blocks.append("\n".join(current))
    return blocks


def build_event_index(catalog: dict[str, Any], business_document: str | Path) -> dict[str, Any]:
    """Tạo event schema/FK/business; mọi node và edge đều có source provenance."""
    business_path = Path(business_document).resolve()
    business_text = business_path.read_text(encoding="utf-8")
    database_id = catalog["database_id"]
    entities: dict[str, dict[str, Any]] = {}
    events: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []

    def entity(kind: str, name: str, source: str) -> str:
        entity_id = _id("entity", database_id, kind, name.casefold())
        current = entities.setdefault(
            entity_id,
            {"id": entity_id, "kind": kind, "name": name, "source": source, "sources": []},
        )
        if source not in current["sources"]:
            current["sources"].append(source)
        return entity_id

    def add_event(kind: str, text: str, source: str, members: list[tuple[str, str]]) -> None:
        event_id = _id("event", database_id, kind, source, text)
        events.append({"id": event_id, "kind": kind, "text": text, "source": source})
        for member_kind, name in members:
            entity_id = entity(member_kind, name, source)
            edges.append(
                {
                    "id": _id("edge", event_id, entity_id),
                    "event_id": event_id,
                    "entity_id": entity_id,
                    "type": "mentions",
                    "source": source,
                }
            )

    table_names = [table["name"] for table in catalog["tables"]]
    column_names = {
        table["name"]: [column["name"] for column in table["columns"]] for table in catalog["tables"]
    }
    for table in catalog["tables"]:
        source = catalog["database_path"]
        members = [("table", table["name"])] + [
            ("column", f"{table['name']}.{column['name']}") for column in table["columns"]
        ]
        add_event(
            "table_structure",
            f"Bảng {table['name']} gồm các cột: {', '.join(column_names[table['name']])}",
            source,
            members,
        )
        for foreign_key in table["foreign_keys"]:
            target_column = foreign_key.get("to_column") or "<unknown>"
            add_event(
                "foreign_key",
                f"{table['name']}.{foreign_key['from_column']} tham chiếu "
                f"{foreign_key['to_table']}.{target_column}",
                source,
                [
                    ("table", table["name"]),
                    ("column", f"{table['name']}.{foreign_key['from_column']}"),
                    ("table", foreign_key["to_table"]),
                    ("column", f"{foreign_key['to_table']}.{target_column}"),
                ],
            )

    known_names = []
    for table in table_names:
        known_names.append(("table", table, re.compile(rf"(?<!\w){re.escape(table)}(?!\w)", re.IGNORECASE)))
        for column in column_names[table]:
            known_names.append(
                ("column", f"{table}.{column}", re.compile(rf"(?<!\w){re.escape(column)}(?!\w)", re.IGNORECASE))
            )
    for section, text in _business_sections(business_text):
        for part, block in enumerate(_bounded_blocks(text), 1):
            compact = re.sub(r"\s+", " ", block).strip()
            if not compact:
                continue
            members = [
                (kind, name)
                for kind, name, pattern in known_names
                if pattern.search(f"{section} {compact}")
            ]
            add_event(
                "business_rule",
                f"{section} [phần {part}]: {compact}",
                str(business_path),
                members,
            )

    payload: dict[str, Any] = {
        "artifact_type": "event_entity_index",
        "artifact_version": 3,
        "database_id": database_id,
        "schema_fingerprint": catalog["fingerprint"],
        "entities": sorted(entities.values(), key=lambda item: item["id"]),
        "events": sorted(events, key=lambda item: item["id"]),
        "edges": sorted(edges, key=lambda item: item["id"]),
    }
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    payload["fingerprint"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return payload


def write_event_index(index: dict[str, Any], destination: str | Path) -> Path:
    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def load_event_index(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))

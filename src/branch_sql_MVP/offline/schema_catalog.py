"""Tạo schema, DDL, foreign-key và value inventory có provenance từ SQLite."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any


def _quote(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _connection(database: str | Path) -> sqlite3.Connection:
    path = Path(database).resolve()
    if not path.is_file():
        raise FileNotFoundError(path)
    connection = sqlite3.connect(f"file:{path.as_posix()}?mode=ro&immutable=1", uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only = ON")
    return connection


def _description_rows(root: str | Path | None) -> dict[tuple[str, str], dict[str, str]]:
    if root is None:
        return {}
    directory = Path(root)
    if not directory.is_dir():
        return {}
    output: dict[tuple[str, str], dict[str, str]] = {}
    for path in sorted(directory.glob("*.csv")):
        raw = path.read_bytes()
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = raw.decode("cp1252")
        for row in csv.DictReader(io.StringIO(text, newline="")):
            column = str(row.get("original_column_name") or "").strip()
            if not column:
                continue
            output[(path.stem.casefold(), column.casefold())] = {
                "business_name": str(row.get("column_name") or "").strip(),
                "description": str(row.get("column_description") or "").strip(),
                "format": str(row.get("data_format") or "").strip(),
                "value_description": str(row.get("value_description") or "").strip(),
                "source": str(path.resolve()),
            }
    return output


def _safe_value(value: Any, max_length: int) -> str | int | float | None:
    if value is None or isinstance(value, bytes):
        return None
    if isinstance(value, (int, float)):
        return value
    text = str(value).strip()
    if not text or len(text) > max_length:
        return None
    return text


def _sample_values(
    connection: sqlite3.Connection,
    table: str,
    column: str,
    *,
    limit: int,
    max_length: int,
) -> tuple[list[Any], bool]:
    if limit <= 0:
        return [], False
    sql = (
        f"SELECT {_quote(column)} AS value FROM {_quote(table)} "
        f"WHERE {_quote(column)} IS NOT NULL LIMIT {max(limit * 8, limit + 1)}"
    )
    unique: list[Any] = []
    seen: set[str] = set()
    for row in connection.execute(sql):
        value = _safe_value(row["value"], max_length)
        if value is None:
            continue
        key = json.dumps(value, ensure_ascii=False, sort_keys=True)
        if key in seen:
            continue
        seen.add(key)
        unique.append(value)
        if len(unique) > limit:
            break
    return unique[:limit], len(unique) > limit


def build_schema_catalog(
    database: str | Path,
    *,
    description_root: str | Path | None = None,
    value_limit: int = 8,
    value_max_length: int = 120,
) -> dict[str, Any]:
    """Đọc schema và lấy mẫu giá trị có giới hạn; không quét cardinality toàn bảng."""
    path = Path(database).resolve()
    descriptions = _description_rows(description_root)
    with closing(_connection(path)) as connection:
        table_rows = connection.execute(
            "SELECT name, sql FROM sqlite_master "
            "WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall()
        primary_keys: dict[str, list[str]] = {}
        raw_columns: dict[str, list[sqlite3.Row]] = {}
        for table in table_rows:
            info = connection.execute(f"PRAGMA table_info({_quote(table['name'])})").fetchall()
            raw_columns[table["name"]] = info
            primary_keys[table["name"].casefold()] = [
                row["name"] for row in sorted(info, key=lambda item: item["pk"]) if row["pk"]
            ]

        tables: list[dict[str, Any]] = []
        for table in table_rows:
            name = table["name"]
            columns = []
            for column in raw_columns[name]:
                details = descriptions.get((name.casefold(), column["name"].casefold()), {})
                values, truncated = _sample_values(
                    connection,
                    name,
                    column["name"],
                    limit=value_limit,
                    max_length=value_max_length,
                )
                columns.append(
                    {
                        "name": column["name"],
                        "type": column["type"],
                        "nullable": not bool(column["notnull"]),
                        "primary_key_position": int(column["pk"]),
                        "default": column["dflt_value"],
                        "business_name": details.get("business_name", ""),
                        "description": details.get("description", ""),
                        "format": details.get("format", ""),
                        "value_description": details.get("value_description", ""),
                        "description_source": details.get("source"),
                        "sample_values": values,
                        "sample_truncated": truncated,
                    }
                )

            foreign_keys = []
            for foreign_key in connection.execute(f"PRAGMA foreign_key_list({_quote(name)})"):
                target_table = str(foreign_key["table"])
                target_column = foreign_key["to"]
                inferred = False
                if not target_column:
                    target_primary_keys = primary_keys.get(target_table.casefold(), [])
                    if len(target_primary_keys) == 1:
                        target_column = target_primary_keys[0]
                        inferred = True
                foreign_keys.append(
                    {
                        "from_column": foreign_key["from"],
                        "to_table": target_table,
                        "to_column": target_column,
                        "target_inferred_from_primary_key": inferred,
                    }
                )
            tables.append(
                {
                    "name": name,
                    "ddl": table["sql"] or "",
                    "columns": columns,
                    "primary_key": primary_keys[name.casefold()],
                    "foreign_keys": foreign_keys,
                }
            )

    payload: dict[str, Any] = {
        "database_id": path.stem,
        "database_path": str(path),
        "value_policy": {
            "method": "bounded_first_non_null_unique_sample",
            "limit_per_column": value_limit,
            "max_string_length": value_max_length,
        },
        "tables": tables,
    }
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    payload["fingerprint"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return payload


def write_schema_catalog(catalog: dict[str, Any], destination: str | Path) -> Path:
    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def load_schema_catalog(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def render_full_ddl(catalog: dict[str, Any]) -> str:
    parts = []
    for table in catalog["tables"]:
        parts.append(str(table["ddl"]).strip().rstrip(";") + ";")
        for foreign_key in table["foreign_keys"]:
            target = foreign_key.get("to_column") or "<unknown>"
            inferred = " (suy ra từ PK)" if foreign_key.get("target_inferred_from_primary_key") else ""
            parts.append(
                f"-- FK {table['name']}.{foreign_key['from_column']} -> "
                f"{foreign_key['to_table']}.{target}{inferred}"
            )
    return "\n\n".join(parts)


def schema_evidence_items(catalog: dict[str, Any]) -> list[dict[str, Any]]:
    output = []
    database_id = catalog["database_id"]
    for table in catalog["tables"]:
        column_names = ", ".join(column["name"] for column in table["columns"])
        output.append(
            {
                "id": f"schema:{database_id}:table:{table['name']}",
                "kind": "schema",
                "text": f"Bảng {table['name']} có các cột: {column_names}",
                "source": catalog["database_path"],
                "metadata": {"database_id": database_id, "table": table["name"]},
            }
        )
        for column in table["columns"]:
            descriptions = " | ".join(
                value
                for value in (
                    column.get("business_name"),
                    column.get("description"),
                    column.get("format"),
                    column.get("value_description"),
                )
                if value
            )
            text = f"{table['name']}.{column['name']} {column['type']}"
            if descriptions:
                text += f": {descriptions}"
            output.append(
                {
                    "id": f"schema:{database_id}:column:{table['name']}:{column['name']}",
                    "kind": "schema",
                    "text": text,
                    "source": column.get("description_source") or catalog["database_path"],
                    "metadata": {
                        "database_id": database_id,
                        "table": table["name"],
                        "column": column["name"],
                    },
                }
            )
            if column["sample_values"]:
                output.append(
                    {
                        "id": f"value:{database_id}:{table['name']}:{column['name']}",
                        "kind": "value",
                        "text": (
                            f"Giá trị mẫu của {table['name']}.{column['name']}: "
                            + ", ".join(map(str, column["sample_values"]))
                        ),
                        "source": catalog["database_path"],
                        "metadata": {
                            "database_id": database_id,
                            "table": table["name"],
                            "column": column["name"],
                            "values": column["sample_values"],
                        },
                    }
                )
    return output

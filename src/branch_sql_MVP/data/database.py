"""Build SQLite fixtures and execute generated SQL through a read-only boundary."""

from __future__ import annotations

import re
import sqlite3
from contextlib import closing
from pathlib import Path
from time import perf_counter

READ_QUERY = re.compile(r"^(?:\s|--[^\n]*\n|/\*.*?\*/)*(SELECT|WITH|EXPLAIN)\b", re.IGNORECASE | re.DOTALL)


def build_sqlite_database(sql_dump: str | Path, destination: str | Path, *, overwrite: bool = False) -> dict:
    source = Path(sql_dump).resolve()
    target = Path(destination).resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    if target.exists() and not overwrite:
        raise FileExistsError(f"{target} đã tồn tại; dùng overwrite=True để tạo lại")
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".building")
    if temporary.exists():
        temporary.unlink()

    started = perf_counter()
    connection = sqlite3.connect(temporary)
    try:
        connection.executescript(source.read_text(encoding="utf-8"))
        violations = connection.execute("PRAGMA foreign_key_check").fetchall()
        if violations:
            raise ValueError(f"SQL dump có {len(violations)} lỗi foreign key")
    except Exception:
        connection.close()
        temporary.unlink(missing_ok=True)
        raise
    else:
        connection.close()
    temporary.replace(target)
    return {
        "path": str(target),
        "size_bytes": target.stat().st_size,
        "elapsed_seconds": round(perf_counter() - started, 3),
        "tables": len(inspect_schema(target)),
    }


def _readonly_connection(database: str | Path) -> sqlite3.Connection:
    path = Path(database).resolve()
    if not path.is_file():
        raise FileNotFoundError(path)
    connection = sqlite3.connect(f"file:{path.as_posix()}?mode=ro&immutable=1", uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only = ON")
    return connection


def inspect_schema(database: str | Path) -> list[dict[str, object]]:
    with closing(_readonly_connection(database)) as connection:
        tables = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall()
        output = []
        for table in tables:
            escaped_name = table["name"].replace('"', '""')
            columns = connection.execute(f'PRAGMA table_info("{escaped_name}")').fetchall()
            output.append(
                {
                    "name": table["name"],
                    "columns": [
                        {
                            "name": row["name"],
                            "type": row["type"],
                            "nullable": not bool(row["notnull"]),
                            "pk": bool(row["pk"]),
                        }
                        for row in columns
                    ],
                }
            )
        return output


def query_readonly(database: str | Path, sql: str, *, limit: int = 200) -> dict[str, object]:
    statement = sql.strip()
    if not statement or not READ_QUERY.match(statement):
        raise ValueError("chỉ chấp nhận một câu SELECT, WITH hoặc EXPLAIN")
    if not 1 <= limit <= 10_000:
        raise ValueError("limit phải trong khoảng 1..10000")

    started = perf_counter()
    with closing(_readonly_connection(database)) as connection:
        cursor = connection.execute(statement)
        rows = cursor.fetchmany(limit + 1)
        columns = [item[0] for item in cursor.description or []]
    truncated = len(rows) > limit
    values = [dict(row) for row in rows[:limit]]
    return {
        "columns": columns,
        "rows": values,
        "row_count": len(values),
        "truncated": truncated,
        "elapsed_seconds": round(perf_counter() - started, 4),
    }

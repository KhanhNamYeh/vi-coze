"""Thực thi SQLite chỉ đọc với policy, timeout và giới hạn kết quả."""

from __future__ import annotations

import re
import sqlite3
from contextlib import closing
from pathlib import Path
from time import perf_counter

from ..pipeline.contracts import ExecutionObservation

READ_QUERY = re.compile(r"^(?:\s|--[^\n]*\n|/\*.*?\*/)*(SELECT|WITH|EXPLAIN)\b", re.IGNORECASE | re.DOTALL)


def classify_execution_error(error: Exception) -> str:
    text = str(error).casefold()
    if "interrupted" in text or "timeout" in text:
        return "timeout"
    if "syntax" in text or "incomplete input" in text:
        return "syntax_error"
    if "no such table" in text or "no such column" in text or "ambiguous column" in text:
        return "missing_object"
    if "datatype" in text or "type mismatch" in text or "misuse" in text:
        return "type_value_error"
    if "authorized" in text or "readonly" in text or "read-only" in text:
        return "policy_violation"
    if "schema" in text:
        return "schema_error"
    return "runtime_error"


def _authorizer(action: int, _arg1: str | None, _arg2: str | None, _db: str | None, _source: str | None) -> int:
    allowed = {
        sqlite3.SQLITE_SELECT,
        sqlite3.SQLITE_READ,
        sqlite3.SQLITE_FUNCTION,
        sqlite3.SQLITE_RECURSIVE,
    }
    return sqlite3.SQLITE_OK if action in allowed else sqlite3.SQLITE_DENY


def execute_readonly_sql(
    database: str | Path,
    sql: str,
    *,
    timeout_seconds: float = 5.0,
    max_rows: int = 500,
    preview_rows: int = 5,
    progress_steps: int = 1_000,
) -> ExecutionObservation:
    statement = sql.strip()
    if not statement or not READ_QUERY.match(statement):
        return ExecutionObservation(status="policy_violation", error="chỉ chấp nhận SELECT, WITH hoặc EXPLAIN")
    if timeout_seconds <= 0 or max_rows < 1 or preview_rows < 0 or progress_steps < 1:
        raise ValueError("tham số execution không hợp lệ")
    path = Path(database).resolve()
    if not path.is_file():
        raise FileNotFoundError(path)
    started = perf_counter()
    try:
        connection = sqlite3.connect(
            f"file:{path.as_posix()}?mode=ro&immutable=1",
            uri=True,
            timeout=min(timeout_seconds, 5.0),
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only = ON")
        deadline = started + timeout_seconds
        connection.set_progress_handler(lambda: 1 if perf_counter() >= deadline else 0, progress_steps)
        connection.set_authorizer(_authorizer)
        with closing(connection):
            cursor = connection.execute(statement)
            rows = cursor.fetchmany(max_rows + 1)
            columns = [str(item[0]) for item in cursor.description or []]
        truncated = len(rows) > max_rows
        kept = rows[:max_rows]
        status = "success" if kept else "empty_result"
        return ExecutionObservation(
            status=status,
            columns=columns,
            preview=[list(row) for row in kept[:preview_rows]],
            row_count=len(kept),
            truncated=truncated,
            elapsed_seconds=round(perf_counter() - started, 6),
        )
    except sqlite3.Error as error:
        return ExecutionObservation(
            status=classify_execution_error(error),
            error=str(error),
            elapsed_seconds=round(perf_counter() - started, 6),
        )

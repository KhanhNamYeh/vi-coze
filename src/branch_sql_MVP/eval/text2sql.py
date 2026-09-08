"""Evaluator SQLite oracle chỉ nhận gold sau khi prediction đã đóng băng."""

from __future__ import annotations

import math
import re
from collections import Counter
from functools import lru_cache
from typing import Any

from ..data.catalog import BenchmarkCase
from ..online.sql_execution import execute_readonly_sql

TABLE_PATTERN = re.compile(r"\b(?:FROM|JOIN)\s+[`\"]?([A-Za-z_][A-Za-z0-9_]*)", re.IGNORECASE)


def referenced_tables(sql: str) -> set[str]:
    return {name.casefold() for name in TABLE_PATTERN.findall(sql)}


def _canonical_value(value: Any) -> tuple[str, Any]:
    if value is None:
        return ("null", None)
    if isinstance(value, bool):
        return ("number", int(value))
    if isinstance(value, (int, float)):
        number = float(value)
        if math.isfinite(number):
            return ("number", round(number, 6))
    return ("text", str(value).strip())


def _canonical_rows(rows: list[list[Any]]) -> list[tuple[tuple[str, Any], ...]]:
    return [tuple(_canonical_value(value) for value in row) for row in rows]


def results_equivalent(
    predicted: dict[str, Any],
    expected: dict[str, Any],
    *,
    order_matters: bool,
) -> bool:
    if predicted["status"] not in {"success", "empty_result"}:
        return False
    if expected["status"] not in {"success", "empty_result"}:
        raise ValueError(f"gold SQL không chạy được: {expected.get('error')}")
    if predicted.get("truncated") or expected.get("truncated"):
        return False
    predicted_rows = _canonical_rows(predicted.get("preview", []))
    expected_rows = _canonical_rows(expected.get("preview", []))
    if predicted_rows and expected_rows and len(predicted_rows[0]) != len(expected_rows[0]):
        return False
    if order_matters:
        return predicted_rows == expected_rows
    return Counter(predicted_rows) == Counter(expected_rows)


def normalize_sql(sql: str) -> str:
    return re.sub(r"\s+", " ", sql.strip().rstrip(";")).casefold()


@lru_cache(maxsize=4096)
def _gold_execution(database_path: str, sql: str, timeout_seconds: float, max_rows: int) -> dict:
    """Cache chỉ ở evaluator; không truyền kết quả oracle vào workflow."""
    return execute_readonly_sql(database_path, sql, timeout_seconds=timeout_seconds,
                                max_rows=max_rows, preview_rows=max_rows).model_dump(mode="json")


def evaluate_prediction(
    case: BenchmarkCase,
    prediction: dict[str, Any],
    database_path: str,
    *,
    timeout_seconds: float = 10.0,
    max_rows: int = 10_000,
) -> dict[str, Any]:
    """Prediction đã là dict bất biến trước khi hàm này được phép đọc `case.gold_sql`."""
    frozen_sql = str(prediction["sql"])
    predicted = execute_readonly_sql(
        database_path,
        frozen_sql,
        timeout_seconds=timeout_seconds,
        max_rows=max_rows,
        preview_rows=max_rows,
    ).model_dump(mode="json")
    gold = _gold_execution(str(database_path), case.gold_sql, timeout_seconds, max_rows)
    order_matters = bool(re.search(r"\bORDER\s+BY\b", case.gold_sql, re.IGNORECASE))
    return {
        "execution_correct": results_equivalent(predicted, gold, order_matters=order_matters)
        if gold["status"] in {"success", "empty_result"} else None,
        "evaluation_error": gold.get("error") if gold["status"] not in {"success", "empty_result"} else None,
        "exact_sql_match": normalize_sql(frozen_sql) == normalize_sql(case.gold_sql),
        "prediction_status": predicted["status"],
        "prediction_error": predicted.get("error"),
        "prediction_rows": predicted.get("row_count", 0),
        "gold_status": gold["status"],
        "order_matters": order_matters,
        "evaluation_protocol": "sqlite_result_equivalence_v1",
    }


def aggregate_results(rows: list[dict[str, Any]]) -> dict[str, Any]:
    completed = [row for row in rows if not row.get("run_error")]
    count = len(rows)
    denominator = max(count, 1)
    evaluation_errors = sum(bool(row.get("evaluation_error")) for row in rows)
    predictions = [row.get("prediction", {}) for row in completed]
    return {
        "cases": count,
        "completed_cases": len(completed),
        "execution_accuracy": sum(bool(row.get("execution_correct")) for row in completed) / max(count - evaluation_errors, 1),
        "evaluable_cases": count - evaluation_errors,
        "evaluation_error_cases": evaluation_errors,
        "evaluation_coverage": (count - evaluation_errors) / denominator,
        "exact_sql_match": sum(bool(row.get("exact_sql_match")) for row in completed) / denominator,
        "invalid_sql_rate": sum(
            row.get("prediction_status") not in {"success", "empty_result"} for row in completed
        )
        / denominator,
        "empty_result_rate": sum(row.get("prediction_status") == "empty_result" for row in completed) / denominator,
        "run_error_rate": sum(bool(row.get("run_error")) for row in rows) / denominator,
        "mean_generation_latency_seconds": sum(float(item.get("latency_seconds", 0)) for item in predictions)
        / max(len(predictions), 1),
        "input_tokens": sum(int(item.get("input_tokens", 0)) for item in predictions),
        "output_tokens": sum(int(item.get("output_tokens", 0)) for item in predictions),
        "mean_repairs": sum(int(row.get("repair_count", 0)) for row in completed) / max(len(completed), 1),
        "mean_candidates": sum(len(row.get("candidates", [])) for row in completed) / max(len(completed), 1),
        "r_ves": None,
        "r_ves_reason": "Chưa tích hợp official BIRD R-VES evaluator; không suy diễn từ execution accuracy.",
    }

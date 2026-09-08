"""Chọn SQL candidate bằng tín hiệu oracle-free từ execution observation."""

from __future__ import annotations

from typing import Any

STATUS_SCORE = {
    "success": 5.0,
    "empty_result": 4.0,
    "runtime_error": 1.0,
    "type_value_error": 1.0,
    "schema_error": 0.5,
    "missing_object": 0.5,
    "syntax_error": 0.0,
    "timeout": -1.0,
    "policy_violation": -2.0,
}


def rank_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    def score(candidate: dict[str, Any]) -> tuple[float, float, int, str]:
        observation = candidate.get("observation") or {}
        prediction = candidate.get("prediction") or {}
        status = observation.get("status", "runtime_error")
        return (
            STATUS_SCORE.get(status, 0.0),
            float(prediction.get("confidence", 0.0)),
            -len(str(prediction.get("sql", ""))),
            str(candidate.get("candidate_id", "")),
        )

    return sorted(candidates, key=score, reverse=True)


def select_best_candidate(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    if not candidates:
        raise ValueError("không có SQL candidate để chọn")
    return rank_candidates(candidates)[0]

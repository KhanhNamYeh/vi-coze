"""Typed shared state cho LangGraph; mọi field nhiều writer có reducer rõ ràng."""

from __future__ import annotations

from operator import add
from typing import Annotated, Any, TypedDict


class WorkflowState(TypedDict, total=False):
    stable_id: str
    split: str
    language: str
    question_id: str
    db_id: str
    question: str
    evidence: str
    difficulty: str
    database_path: str
    business_path: str
    schema_catalog_path: str
    event_index_path: str
    context_parameters: dict[str, Any]
    execution_parameters: dict[str, Any]
    route_parameters: dict[str, Any]
    scenario: str
    context_text: str
    evidence_items: list[dict[str, Any]]
    route: str
    candidate_strategy: str
    candidate_strategies: list[str]
    candidates: Annotated[list[dict[str, Any]], add]
    observations: list[dict[str, Any]]
    final_prediction: dict[str, Any]
    repair_count: int
    max_repairs: int
    trajectory: Annotated[list[dict[str, Any]], add]


class CandidateWorkerState(TypedDict):
    stable_id: str
    question: str
    evidence: str
    context_text: str
    candidate_strategy: str
    candidates: Annotated[list[dict[str, Any]], add]
    trajectory: Annotated[list[dict[str, Any]], add]

"""Contract có thể serialize dùng chung giữa workflow, runner và evaluator."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

EvidenceKind = Literal["schema", "value", "business", "example", "event"]
ExecutionStatus = Literal[
    "success",
    "empty_result",
    "syntax_error",
    "schema_error",
    "missing_object",
    "type_value_error",
    "timeout",
    "policy_violation",
    "runtime_error",
]


class EvidenceItem(BaseModel):
    id: str = Field(min_length=1)
    kind: EvidenceKind
    text: str = Field(min_length=1)
    source: str = Field(min_length=1)
    score: float = 0.0
    metadata: dict[str, Any] = Field(default_factory=dict)


class SQLPrediction(BaseModel):
    sql: str = Field(min_length=1)
    confidence: float = Field(default=0.5, ge=0, le=1)
    assumptions: list[str] = Field(default_factory=list)
    model: str = ""
    prompt_version: str = ""
    latency_seconds: float = Field(default=0.0, ge=0)
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def one_statement(self):
        sql = self.sql.strip()
        if sql.startswith("```"):
            raise ValueError("SQL prediction không được chứa Markdown fence")
        if not sql:
            raise ValueError("SQL prediction rỗng")
        self.sql = sql.rstrip(";").strip() + ";"
        return self


class ExecutionObservation(BaseModel):
    status: ExecutionStatus
    error: str | None = None
    columns: list[str] = Field(default_factory=list)
    preview: list[list[Any]] = Field(default_factory=list)
    row_count: int = Field(default=0, ge=0)
    truncated: bool = False
    elapsed_seconds: float = Field(default=0.0, ge=0)

    @property
    def terminal(self) -> bool:
        return self.status in {"success", "empty_result"}


class CandidateRecord(BaseModel):
    candidate_id: str
    strategy: str
    prediction: SQLPrediction
    observation: ExecutionObservation | None = None


class RunManifest(BaseModel):
    run_id: str
    scenario: Literal["P1", "B4", "B5", "B6", "G1"]
    split: Literal["dev", "test"]
    model_provider: str
    model: str
    prompt_version: str
    dataset_fingerprint: str
    index_fingerprint: str | None = None
    dependency_lock_sha256: str
    seed: int
    hardware: dict[str, Any]
    parameters: dict[str, Any]
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())


class CaseResult(BaseModel):
    stable_id: str
    scenario: Literal["P1", "B4", "B5", "B6", "G1"]
    prediction: SQLPrediction
    observation: ExecutionObservation | None = None
    route: str | None = None
    candidates: list[CandidateRecord] = Field(default_factory=list)
    evidence: list[EvidenceItem] = Field(default_factory=list)
    trajectory: list[dict[str, Any]] = Field(default_factory=list)
    repair_count: int = Field(default=0, ge=0)


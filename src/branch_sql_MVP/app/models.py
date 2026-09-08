"""Validated request contracts for the HTTP API."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class SourceRequest(BaseModel):
    source: str


class DocumentRequest(BaseModel):
    doc_id: str


class ExtractRequest(BaseModel):
    markdown_path: str


class IndexRequest(DocumentRequest):
    knowledge_id: str
    kind: str
    recreate: bool | None = None


class GraphRequest(DocumentRequest):
    kind: Literal["docs", "sql"] = "docs"
    provider: str | None = None
    model: str | None = None
    api_key: str | None = None


class PipelineRequest(SourceRequest):
    knowledge_id: str
    kind: str
    recreate: bool | None = None
    graph_provider: str | None = None
    graph_model: str | None = None
    graph_api_key: str | None = None


class RetrievalRequest(BaseModel):
    query: str
    knowledge_id: str
    kind: Literal["docs", "sql", "graph"]
    mode: Literal["semantic", "keyword", "hybrid"] | None = None
    semantic_weight: float | None = Field(None, ge=0)
    keyword_weight: float | None = Field(None, ge=0)


class ChatRequest(BaseModel):
    query: str
    knowledge_id: str
    provider: str | None = None
    model: str | None = None
    api_key: str | None = None
    mode: Literal["semantic", "keyword", "hybrid"] | None = None
    semantic_weight: float | None = Field(None, ge=0)
    keyword_weight: float | None = Field(None, ge=0)


class GraphEvalRequest(DocumentRequest):
    knowledge_id: str
    split: Literal["dev", "test"] = "dev"


class DatabaseBuildRequest(BaseModel):
    overwrite: bool = False


class DatabaseQueryRequest(BaseModel):
    sql: str
    limit: int = Field(200, ge=1, le=10_000)

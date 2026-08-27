"""Một file settings dùng chung cho preprocess, offline, online và app."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

ROOT = Path(__file__).resolve().parents[2]
SETTINGS_FILE = Path(__file__).with_name("settings.json")


class Paths(BaseModel):
    raw: str = "data/raw/sql"
    markdown: str = "data/processed/sql_mvp/markdown"
    artifacts: str = "data/processed/sql_mvp/offline"
    eval: str = "data/eval/sql_mvp"


class PreprocessSettings(BaseModel):
    excel_sheets: list[str] = Field(default_factory=list)
    excel_id_column: int | str = 0
    excel_exclude_features: list[str] = Field(default_factory=lambda: ["Relevant Chunks"])
    record_heading_level: int = Field(2, ge=1, le=6)
    feature_heading_level: int = Field(3, ge=1, le=6)
    overwrite: bool = True


class ChunkSettings(BaseModel):
    unit: Literal["token", "character"] = "token"
    tokenizer_model: str | None = None
    heading_level: int = Field(2, ge=1, le=6)
    child_min: int = Field(40, ge=0)
    child_max: int = Field(512, gt=0)
    child_overlap: int = Field(32, ge=0)
    parent_max: int = Field(3000, gt=0)
    table_rows: int = Field(10, gt=0)
    table_overlap_rows: int = Field(1, ge=0)
    repeat_table_header: bool = True
    separators: list[str] = Field(default_factory=lambda: ["\n\n", "\n", ". ", " ", ""])
    on_overflow: Literal["split", "truncate"] = "split"
    on_underflow: Literal["keep", "merge", "drop"] = "merge"
    breadcrumb: bool = True

    @model_validator(mode="after")
    def validate_limits(self):
        if self.child_min > self.child_max:
            raise ValueError("chunk.child_min không được lớn hơn child_max")
        if self.child_overlap >= self.child_max:
            raise ValueError("chunk.child_overlap phải nhỏ hơn child_max")
        if self.table_overlap_rows >= self.table_rows:
            raise ValueError("table_overlap_rows phải nhỏ hơn table_rows")
        return self


class EmbeddingSettings(BaseModel):
    dense_model: str = "AITeamVN/Vietnamese_Embedding"
    sparse_model: str = "Qdrant/bm25"
    rerank_model: str = "AITeamVN/Vietnamese_Reranker"
    device: str = "cuda"
    batch_size: int = Field(16, gt=0)
    normalize: bool = True
    bm25_k: float = Field(1.2, gt=0)
    bm25_b: float = Field(0.0, ge=0)
    disable_stemmer: bool = True


class GraphSettings(BaseModel):
    enabled: bool = True
    source_kinds: list[Literal["docs", "sql"]] = Field(default_factory=lambda: ["docs", "sql"])
    method: Literal["llm"] = "llm"
    provider: str | None = None
    model: str | None = None
    temperature: float = Field(0.0, ge=0, le=2)
    output_retries: int = Field(1, ge=0, le=3)
    entity_types: list[str] = Field(default_factory=lambda: [
        "table", "column", "metric", "business_rule", "filter_value", "sql_function",
    ])
    relationship_types: list[str] = Field(default_factory=lambda: [
        "table_has_column", "foreign_key_to", "joins_with", "metric_uses_column",
        "rule_applies_to", "derived_from", "uses", "filters_by", "aliases",
    ])
    community_algorithm: Literal["louvain", "greedy_modularity", "connected_components"] = "louvain"
    community_resolution: float = Field(1.0, gt=0)
    random_seed: int = 42
    generate_reports: bool = True
    max_reports: int = Field(30, ge=0)
    max_chunks: int = Field(0, ge=0)
    visualization_max_nodes: int = Field(120, gt=0)
    agent_prompt: str = (
        "You are a neutral SQL knowledge-graph agent. Extract only facts explicitly supported "
        "by the supplied chunk. Use only the allowed entity and relationship types, make every "
        "relationship endpoint exactly match an extracted entity name, and attach a short "
        "verbatim evidence span to every entity and relationship. Do not infer missing schema."
    )
    report_prompt: str = (
        "You are the same neutral SQL knowledge-graph agent. Summarize only the supplied graph "
        "community for retrieval. Preserve table, column, join, metric and business-rule facts; "
        "do not add facts that are absent from the community."
    )

    @model_validator(mode="after")
    def validate_graph(self):
        if not self.source_kinds:
            raise ValueError("graph.source_kinds không được rỗng")
        if not self.entity_types or not self.relationship_types:
            raise ValueError("graph entity_types và relationship_types không được rỗng")
        return self


class IndexSettings(BaseModel):
    url: str = "http://localhost:6333"
    local_path: str | None = None
    api_key_env: str | None = "QDRANT_API_KEY"
    knowledge_id: str = "p1"
    collections: dict[str, dict[str, str]] = Field(default_factory=lambda: {
        "p1": {"docs": "sqlp1__docs", "sql": "sqlp1__sql", "graph": "sqlp1__graph"},
        "p2": {"docs": "sqlp2__docs", "sql": "sqlp2__sql", "graph": "sqlp2__graph"},
    })
    dense_vector: str = "dense"
    sparse_vector: str = "bm25"
    batch_size: int = Field(64, gt=0)
    recreate: bool = False

    @model_validator(mode="after")
    def validate_collections(self):
        if self.knowledge_id not in self.collections:
            raise ValueError(f"index.knowledge_id '{self.knowledge_id}' chưa được khai báo")
        for knowledge_id, collections in self.collections.items():
            missing = {"docs", "sql", "graph"} - set(collections)
            if missing:
                raise ValueError(f"knowledge '{knowledge_id}' thiếu collection: {', '.join(sorted(missing))}")
        return self

    def collection(self, knowledge_id: str, kind: str) -> str:
        if knowledge_id not in self.collections:
            raise ValueError(f"knowledge_id '{knowledge_id}' không hợp lệ; có: {', '.join(self.collections)}")
        if kind not in self.collections[knowledge_id]:
            raise ValueError(f"kind '{kind}' không hợp lệ; có: docs, sql, graph")
        return self.collections[knowledge_id][kind]


class RetrievalSettings(BaseModel):
    mode: Literal["semantic", "keyword", "hybrid"] = "hybrid"
    candidate_k: int = Field(20, gt=0)
    docs_top_k: int = Field(5, gt=0)
    sql_top_k: int = Field(3, gt=0)
    graph_top_k: int = Field(3, gt=0)
    semantic_weight: float = Field(0.5, ge=0)
    keyword_weight: float = Field(0.5, ge=0)
    rrf_k: int = Field(40, gt=0)
    rerank_top_k: int = Field(8, gt=0)
    min_score: float | None = None

    @model_validator(mode="after")
    def validate_retrieval(self):
        if self.semantic_weight + self.keyword_weight <= 0:
            raise ValueError("ít nhất một retrieval weight phải lớn hơn 0")
        if self.candidate_k < max(self.docs_top_k, self.sql_top_k, self.graph_top_k):
            raise ValueError("candidate_k phải lớn hơn hoặc bằng top_k")
        return self


class ProviderSettings(BaseModel):
    binding: Literal["openai", "google", "nvidia"]
    api_key_env: str
    base_url: str | None = None
    base_url_env: str | None = None
    headers: dict[str, str] = Field(default_factory=dict)


class APISettings(BaseModel):
    provider: str = "openai"
    model: str = "gpt-5.4"
    timeout: float = Field(60, gt=0)
    retries: int = Field(2, ge=0)
    providers: dict[str, ProviderSettings]

    @model_validator(mode="after")
    def known_provider(self):
        if self.provider not in self.providers:
            raise ValueError(f"api.provider '{self.provider}' chưa được khai báo")
        return self


class LLMSettings(BaseModel):
    system_prompt: str = "Bạn là trợ lý Text-to-SQL. Chỉ dùng ngữ cảnh được cung cấp."
    temperature: float | None = Field(None, ge=0, le=2)
    max_tokens: int | None = Field(None, gt=0)
    top_p: float | None = Field(None, gt=0, le=1)
    stop: list[str] = Field(default_factory=list)
    structured_output: dict[str, Any] | None = None
    extra: dict[str, Any] = Field(default_factory=dict)


class EvalSettings(BaseModel):
    source: str = "Text2SQL_testcase.xlsx"
    split: Literal["dev", "test"] = "dev"
    id_column: str = "Test Case ID"
    query_column: str = "Query"
    relevant_column: str = "Relevant Chunks"
    separator: str = "|"


class Settings(BaseModel):
    paths: Paths = Field(default_factory=Paths)
    preprocess: PreprocessSettings = Field(default_factory=PreprocessSettings)
    chunk: ChunkSettings = Field(default_factory=ChunkSettings)
    embedding: EmbeddingSettings = Field(default_factory=EmbeddingSettings)
    graph: GraphSettings = Field(default_factory=GraphSettings)
    index: IndexSettings = Field(default_factory=IndexSettings)
    retrieval: RetrievalSettings = Field(default_factory=RetrievalSettings)
    api: APISettings
    llm: LLMSettings = Field(default_factory=LLMSettings)
    eval: EvalSettings = Field(default_factory=EvalSettings)

    model_config = {"extra": "forbid"}

    def path(self, value: str) -> Path:
        path = Path(value)
        return path if path.is_absolute() else ROOT / path


def load_settings(path: Path = SETTINGS_FILE) -> Settings:
    return Settings.model_validate_json(path.read_text(encoding="utf-8"))


def update_settings(patch: dict[str, Any], path: Path = SETTINGS_FILE) -> Settings:
    """Merge patch rồi validate trước khi ghi; secret không thuộc schema này."""
    def merge(base: dict[str, Any], change: dict[str, Any]) -> dict[str, Any]:
        out = dict(base)
        for key, value in change.items():
            current = out.get(key)
            out[key] = merge(current, value) if isinstance(current, dict) and isinstance(value, dict) else value
        return out

    current = load_settings(path).model_dump()
    settings = Settings.model_validate(merge(current, patch))
    path.write_text(
        json.dumps(settings.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return settings

"""Typed contracts for the Dify-style workflow editor.

The contract deliberately separates a reusable node *type* from a configured
node instance. It is safe to serialize because references are data, never code.
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


# Values in workflows are stored on disk and can be exported.  Keep the list
# deliberately exact: configuration such as ``max_tokens`` and
# ``token_budget`` is safe and must remain usable.
_SECRET_KEYS = {
    "api_key",
    "secret",
    "password",
    "access_token",
    "authorization",
    "bearer_token",
}


def _is_secret_key(key: object) -> bool:
    normalized = str(key).casefold().replace("-", "_")
    return normalized in _SECRET_KEYS or normalized.endswith("_api_key")


class Reference(BaseModel):
    model_config = ConfigDict(extra="forbid")
    node_id: str | None = None
    output: str | None = None
    value: Any = None

    @model_validator(mode="after")
    def one_source(self):
        has_ref = self.node_id is not None or self.output is not None
        has_value = self.value is not None or (not has_ref and "value" in self.model_fields_set)
        if has_ref == has_value:
            raise ValueError("reference cần đúng một nguồn node/output hoặc value")
        if has_ref and (not self.node_id or not self.output):
            raise ValueError("reference node cần node_id và output")
        return self


class Edge(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source: str
    target: str
    condition: str | None = None


class NodeInstance(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_-]{0,63}$")
    type: str
    label: str
    config: dict[str, Any] = Field(default_factory=dict)
    inputs: dict[str, Reference] = Field(default_factory=dict)
    position: dict[str, float] = Field(default_factory=lambda: {"x": 0, "y": 0})


class WorkflowDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: str = "1"
    id: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_-]{0,63}$")
    revision: int = Field(default=1, ge=1)
    kind: Literal["online", "offline"]
    name: str = ""
    description: str = ""
    requires_index: bool = False
    nodes: list[NodeInstance]
    edges: list[Edge] = Field(default_factory=list)
    outputs: dict[str, Reference] = Field(default_factory=dict)
    defaults: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_graph(self):
        ids = [node.id for node in self.nodes]
        if len(ids) != len(set(ids)):
            raise ValueError("node id bị trùng")
        known = set(ids)
        for edge in self.edges:
            if edge.source not in known or edge.target not in known:
                raise ValueError("edge tham chiếu node không tồn tại")
            if edge.source == edge.target and not edge.condition:
                raise ValueError("self-loop cần condition/loop guard")
        for node in self.nodes:
            for reference in node.inputs.values():
                if reference.node_id and reference.node_id not in known:
                    raise ValueError(f"input của {node.id} tham chiếu node không tồn tại")
        for reference in self.outputs.values():
            if reference.node_id and reference.node_id not in known:
                raise ValueError("output tham chiếu node không tồn tại")
        # Repetition lives in bounded composite nodes. Each child definition is
        # a DAG, so raw cycles cannot bypass the explicit iteration bound.
        adjacency: dict[str, list[str]] = {node_id: [] for node_id in known}
        for edge in self.edges:
            adjacency[edge.source].append(edge.target)
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(node_id: str) -> None:
            if node_id in visiting:
                raise ValueError("cycle chỉ được hỗ trợ qua bounded-loop node")
            if node_id in visited:
                return
            visiting.add(node_id)
            for target in adjacency[node_id]:
                visit(target)
            visiting.remove(node_id)
            visited.add(node_id)

        for node_id in known:
            visit(node_id)
        def inspect(value: Any, path: str = "config"):
            if isinstance(value, dict):
                for key, item in value.items():
                    if _is_secret_key(key):
                        raise ValueError(f"secret không được lưu trong workflow: {path}.{key}")
                    inspect(item, f"{path}.{key}")
            elif isinstance(value, list):
                for index, item in enumerate(value):
                    inspect(item, f"{path}[{index}]")
        for node in self.nodes:
            inspect(node.config, f"node.{node.id}.config")
        inspect(self.defaults, "defaults")
        for node in self.nodes:
            inspect({key: ref.value for key, ref in node.inputs.items() if ref.node_id is None}, f"node.{node.id}.inputs")
        inspect({key: ref.value for key, ref in self.outputs.items() if ref.node_id is None}, "outputs")
        return self

"""Compile a validated definition into a real LangGraph linear workflow."""
from __future__ import annotations
from typing import Annotated, Any, TypedDict
from operator import or_
from uuid import uuid4
from copy import deepcopy
from langgraph.graph import END, START, StateGraph
from .contracts import WorkflowDefinition
from .registry import node_registry


def _read_output(value: Any, path: str) -> Any:
    """Resolve ``node.output.nested`` without executing user supplied code."""
    current = value
    if path == "$":
        return current
    for component in path.split("."):
        if isinstance(current, dict) and component in current:
            current = current[component]
        elif isinstance(current, list) and component.isdigit() and int(component) < len(current):
            current = current[int(component)]
        else:
            raise ValueError(f"không tìm thấy output '{path}'")
    return current


def _resolve(inputs: dict[str, Any], values: dict[str, dict[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, ref in inputs.items():
        result[key] = _read_output(values.get(ref.node_id, {}), ref.output) if ref.node_id else ref.value
    return result


def resolve_workflow_outputs(definition: WorkflowDefinition, values: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Resolve declared workflow outputs from one completed run."""
    return _resolve(definition.outputs, values)

def merge_invocations(left, right):
    collision = set(left) & set(right)
    if collision:
        raise ValueError(f"invocation collision: {sorted(collision)}")
    return {**left, **right}


class _RunState(TypedDict, total=False):
    inputs: dict[str, Any]
    invocations: Annotated[dict[str, dict[str, Any]], merge_invocations]
    node_outputs: Annotated[dict[str, dict[str, Any]], or_]


def compile_workflow(definition: WorkflowDefinition, *, settings=None, emit=None, cancelled=None, api_key=None):
    from ..settings import load_settings
    settings = (settings or load_settings()).model_copy(deep=True)
    definition = definition.model_copy(deep=True)
    registry = node_registry()
    for node in definition.nodes:
        if node.type not in registry:
            raise ValueError(f"node type không tồn tại: {node.type}")
        from jsonschema import validate, ValidationError, SchemaError
        try:
            validate(node.config,registry[node.type].config_schema)
        except (ValidationError,SchemaError) as error:
            raise ValueError(f"Invalid config at {node.id}: {error.message}") from error
    by_id = {node.id: node for node in definition.nodes}
    for node in definition.nodes:
        for ref in node.inputs.values():
            if ref.node_id and ref.output != "$":
                source = by_id[ref.node_id]
                schema = registry[source.type].output_schema
                if source.type == "bounded_loop":
                    schema = {**schema, **{k: {} for k in source.config.get("body", {}).get("outputs", {})}}
                parts = ref.output.split(".")
                if source.type == "llm" and parts[0] == "json" and len(parts) > 1:
                    schema = source.config.get("output_schema", {})
                    for part in parts[1:]:
                        if schema.get("properties") and part not in schema["properties"]:
                            raise ValueError(f"Unknown JSON output: {ref.output}")
                        schema = schema.get("properties", {}).get(part, {})
                elif schema and parts[0] not in schema and source.type != "start":
                    raise ValueError(f"Unknown output: {ref.node_id}.{ref.output}")
        if node.type in {"bounded_loop", "foreach"}:
            maximum = node.config.get("max_iterations" if node.type == "bounded_loop" else "max_items")
            if not isinstance(maximum, int) or isinstance(maximum, bool) or not 1 <= maximum <= (100000 if node.type == "foreach" else 100):
                raise ValueError(f"{node.type} requires an integer bound between 1 and 100")
            body = WorkflowDefinition.model_validate(node.config.get("body", {}))
            compile_workflow(body, settings=settings)
    graph = StateGraph(_RunState)
    def make_node(node):
        spec = registry[node.type]
        def run(state: dict[str, Any]) -> dict[str, Any]:
            if cancelled and cancelled():
                raise InterruptedError("run cancelled at node boundary")
            invocation_id = uuid4().hex
            values = dict(state.get("node_outputs", {}))
            inputs = {}
            if spec.executor is None:
                raise RuntimeError(f"node type chưa có executor: {node.type}")
            try:
                inputs = _resolve(node.inputs, values)
                if "$" in inputs:
                    base = inputs.pop("$")
                    if not isinstance(base, dict):
                        raise ValueError("Spread input must resolve to an object")
                    inputs = {**base, **inputs}
                if emit:
                    emit("node_started", node_id=node.id, invocation_id=invocation_id, inputs=inputs)
                if node.type in {"bounded_loop", "foreach"}:
                    body = WorkflowDefinition.model_validate(node.config["body"])
                    def nested_emit(event, **data):
                        child_scope = data.pop("scope", "")
                        scope = node.id + "/" + invocation_id
                        if child_scope:
                            scope += "/" + child_scope
                        emit(event, scope=scope, **data)
                    nested = compile_workflow(body, settings=settings,
                        emit=nested_emit if emit else None,
                        cancelled=cancelled, api_key=api_key)
                    runs = []
                    if node.type == "foreach":
                        items = inputs.get("items")
                        if not isinstance(items, list) or len(items) > node.config["max_items"]:
                            raise ValueError("foreach items must be an array within max_items")
                        def one(pair):
                            index, item = pair
                            child = nested.invoke({"inputs": {**inputs, "item": item, "index": index}, "node_outputs": {}})
                            return {"outputs": resolve_workflow_outputs(body, child["node_outputs"]), "invocations": child["invocations"]}
                        from concurrent.futures import ThreadPoolExecutor
                        with ThreadPoolExecutor(max_workers=min(3, max(1, len(items)))) as pool:
                            runs = list(pool.map(one, enumerate(items)))
                        output = {"items": [r["outputs"] for r in runs], "iterations": runs}
                    else:
                        current = dict(inputs)
                        for index in range(node.config["max_iterations"]):
                            child = nested.invoke({"inputs": {**current, "iteration": index}, "node_outputs": {}})
                            resolved = resolve_workflow_outputs(body, child["node_outputs"])
                            repeat_path = node.config.get("stop_on_repeat_output")
                            if repeat_path and resolved.get("continue"):
                                previous = _read_output(current,repeat_path)
                                following = _read_output(resolved,repeat_path)
                                if str(previous).strip().rstrip(';') == str(following).strip().rstrip(';'):
                                    resolved.update({"continue":False,"stop_reason":"repeated_output"})
                            runs.append({"outputs": resolved, "invocations": child["invocations"]})
                            current.update(resolved)
                            if not resolved.get("continue", False):
                                break
                        output = {**current, "iterations": runs, "bound_reached": bool(current.get("continue", False))}
                else:
                    output = spec.executor(inputs, node.config, state=state, settings=settings,
                                           api_key=api_key)
            except Exception as error:
                if emit:
                    emit("node_failed", node_id=node.id, invocation_id=invocation_id, error=str(error))
                raise
            record = {"node_id": node.id, "inputs": inputs, "output": output}
            if emit:
                emit("node_completed", node_id=node.id, invocation_id=invocation_id, output=output)
            return {"node_outputs": {node.id: output}, "invocations": {invocation_id: record}}
        return run
    for node in definition.nodes:
        graph.add_node(node.id, make_node(node))
    incoming = {node.id: 0 for node in definition.nodes}
    outgoing = {node.id: 0 for node in definition.nodes}
    conditional_sources = set()
    for edge in definition.edges:
        if edge.condition:
            conditional_sources.add(edge.source)
        else:
            target_node = next(n for n in definition.nodes if n.id == edge.target)
            parents = [e.source for e in definition.edges if e.target == edge.target and not e.condition]
            if len(parents) < 2 or target_node.type == "merge":
                graph.add_edge(edge.source, edge.target)
            elif edge.source == parents[0]:
                graph.add_edge(parents, edge.target)
        incoming[edge.target] += 1
        outgoing[edge.source] += 1
    roots = [node.id for node in definition.nodes if incoming[node.id] == 0]
    if not roots:
        raise ValueError("workflow không có node đầu vào")
    for root in roots:
        graph.add_edge(START, root)
    for source in conditional_sources:
        conditional = [edge for edge in definition.edges if edge.source == source and edge.condition]
        mapping = {edge.condition: edge.target for edge in conditional}
        if len(mapping) != len(conditional):
            raise ValueError(f"condition trùng tại node {source}")
        graph.add_conditional_edges(source, lambda state, source=source: state["node_outputs"][source].get("route"), mapping)
    for leaf in [node.id for node in definition.nodes if outgoing[node.id] == 0]:
        graph.add_edge(leaf, END)
    return graph.compile()

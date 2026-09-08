"""Workflow hybrid linked context cố định, không execution feedback."""

from __future__ import annotations

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from ..online.context_builder import build_linked_context, load_optional_example_index
from ..online.llm import generate_sql_candidate
from ..settings import Settings
from .state import WorkflowState


def build_hybrid_workflow(
    settings: Settings,
    *,
    provider: str | None = None,
    model: str | None = None,
    api_key: str | None = None,
):
    def assemble_linked_context(state: WorkflowState) -> dict:
        parameters = state.get("context_parameters", {})
        example_index = load_optional_example_index(parameters.get("example_index_path"))
        context, items, trace = build_linked_context(
            state["question"],
            state.get("evidence", ""),
            state["schema_catalog_path"],
            knowledge_id=str(parameters["knowledge_id"]),
            doc_id=str(parameters["doc_id"]),
            settings=settings,
            parameters=parameters,
            example_index=example_index,
        )
        return {
            "context_text": context,
            "evidence_items": items,
            "trajectory": [{"node": "assemble_linked_context", "trace": trace}],
        }

    def generate_linked_candidate(state: WorkflowState) -> dict:
        prediction = generate_sql_candidate(
            state["question"],
            state["context_text"],
            strategy="hybrid_linked_context",
            settings=settings,
            provider=provider,
            model=model,
            api_key=api_key,
        ).model_dump(mode="json")
        candidate = {"candidate_id": "candidate_1", "strategy": "hybrid_linked_context", "prediction": prediction}
        return {
            "candidates": [candidate],
            "final_prediction": prediction,
            "trajectory": [{"node": "generate_linked_candidate", "candidate_id": "candidate_1"}],
        }

    builder = StateGraph(WorkflowState)
    builder.add_node("assemble_linked_context", assemble_linked_context)
    builder.add_node("generate_linked_candidate", generate_linked_candidate)
    builder.add_edge(START, "assemble_linked_context")
    builder.add_edge("assemble_linked_context", "generate_linked_candidate")
    builder.add_edge("generate_linked_candidate", END)
    return builder.compile(checkpointer=InMemorySaver())


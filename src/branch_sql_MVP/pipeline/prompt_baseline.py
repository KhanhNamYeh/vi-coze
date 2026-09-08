"""Workflow full-context one-shot: assemble context rồi sinh đúng một SQL."""

from __future__ import annotations

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from ..online.context_builder import build_full_context
from ..online.llm import generate_sql_candidate
from ..settings import Settings
from .state import WorkflowState


def build_prompt_workflow(
    settings: Settings,
    *,
    provider: str | None = None,
    model: str | None = None,
    api_key: str | None = None,
):
    def assemble_full_context(state: WorkflowState) -> dict:
        context, items, stats = build_full_context(
            state["question"],
            state.get("evidence", ""),
            state["schema_catalog_path"],
            state["business_path"],
        )
        return {
            "context_text": context,
            "evidence_items": items,
            "trajectory": [{"node": "assemble_full_context", **stats}],
        }

    def generate_one_candidate(state: WorkflowState) -> dict:
        prediction = generate_sql_candidate(
            state["question"],
            state["context_text"],
            strategy="one_shot_full_context",
            settings=settings,
            provider=provider,
            model=model,
            api_key=api_key,
        ).model_dump(mode="json")
        candidate = {"candidate_id": "candidate_1", "strategy": "one_shot_full_context", "prediction": prediction}
        return {
            "candidates": [candidate],
            "final_prediction": prediction,
            "trajectory": [{"node": "generate_one_candidate", "candidate_id": "candidate_1"}],
        }

    builder = StateGraph(WorkflowState)
    builder.add_node("assemble_full_context", assemble_full_context)
    builder.add_node("generate_one_candidate", generate_one_candidate)
    builder.add_edge(START, "assemble_full_context")
    builder.add_edge("assemble_full_context", "generate_one_candidate")
    builder.add_edge("generate_one_candidate", END)
    return builder.compile(checkpointer=InMemorySaver())


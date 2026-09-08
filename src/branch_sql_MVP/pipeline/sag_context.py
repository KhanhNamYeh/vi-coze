"""Workflow relational context: linked evidence, event expansion và selector tách biệt."""

from __future__ import annotations

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from ..offline.event_index import load_event_index
from ..online.context_builder import (
    build_linked_context,
    load_optional_example_index,
    select_evidence_bundle,
)
from ..online.llm import generate_sql_candidate, select_contextual_evidence
from ..online.sag_retrieval import expand_event_neighborhood, retrieve_seed_events
from ..settings import Settings
from .state import WorkflowState


def _render(items: list[dict]) -> str:
    return "\n\n".join(
        f"[{item['kind'].upper()} id={item['id']} source={item['source']}]\n{item['text']}" for item in items
    )


def build_relational_workflow(
    settings: Settings,
    *,
    provider: str | None = None,
    model: str | None = None,
    api_key: str | None = None,
):
    def assemble_linked_context(state: WorkflowState) -> dict:
        parameters = state.get("context_parameters", {})
        context, items, trace = build_linked_context(
            state["question"],
            state.get("evidence", ""),
            state["schema_catalog_path"],
            knowledge_id=str(parameters["knowledge_id"]),
            doc_id=str(parameters["doc_id"]),
            settings=settings,
            parameters=parameters,
            example_index=load_optional_example_index(parameters.get("example_index_path")),
        )
        return {
            "context_text": context,
            "evidence_items": items,
            "trajectory": [{"node": "assemble_linked_context", "trace": trace}],
        }

    def expand_relational_context(state: WorkflowState) -> dict:
        parameters = state.get("context_parameters", {})
        if not parameters.get("use_events", True):
            return {"trajectory": [{"node": "expand_relational_context", "skipped": True}]}
        index = load_event_index(state["event_index_path"])
        seeds = retrieve_seed_events(
            state["question"],
            state["evidence_items"],
            index,
            top_k=int(parameters.get("event_top_k", 8)),
        )
        events = expand_event_neighborhood(
            seeds,
            index,
            hops=int(parameters.get("event_hops", 1)) if parameters.get("expand_events", True) else 0,
            node_budget=int(parameters.get("event_node_budget", 24)),
            token_budget=int(parameters.get("event_token_budget", 1800)),
        )
        combined = [*state["evidence_items"], *events]
        return {
            "evidence_items": combined,
            "context_text": _render(combined),
            "trajectory": [
                {
                    "node": "expand_relational_context",
                    "seed_event_ids": seeds,
                    "event_items": len(events),
                    "hops": int(parameters.get("event_hops", 1)),
                }
            ],
        }

    def select_relational_evidence(state: WorkflowState) -> dict:
        parameters = state.get("context_parameters", {})
        items = state["evidence_items"]
        if parameters.get("contextual_selector", True):
            selected, trace = select_contextual_evidence(
                state["question"],
                items,
                max_items=int(parameters.get("selector_max_items", 24)),
                settings=settings,
                provider=provider,
                model=model,
                api_key=api_key,
            )
        else:
            selected, budget_trace = select_evidence_bundle(
                items,
                token_budget=int(parameters.get("token_budget", 5000)),
            )
            trace = {"mode": "deterministic_budget", "items": budget_trace}
        return {
            "evidence_items": selected,
            "context_text": _render(selected),
            "trajectory": [{"node": "select_relational_evidence", **trace}],
        }

    def generate_relational_candidate(state: WorkflowState) -> dict:
        prediction = generate_sql_candidate(
            state["question"],
            state["context_text"],
            strategy="relational_context",
            settings=settings,
            provider=provider,
            model=model,
            api_key=api_key,
        ).model_dump(mode="json")
        candidate = {"candidate_id": "candidate_1", "strategy": "relational_context", "prediction": prediction}
        return {
            "candidates": [candidate],
            "final_prediction": prediction,
            "trajectory": [{"node": "generate_relational_candidate", "candidate_id": "candidate_1"}],
        }

    builder = StateGraph(WorkflowState)
    builder.add_node("assemble_linked_context", assemble_linked_context)
    builder.add_node("expand_relational_context", expand_relational_context)
    builder.add_node("select_relational_evidence", select_relational_evidence)
    builder.add_node("generate_relational_candidate", generate_relational_candidate)
    builder.add_edge(START, "assemble_linked_context")
    builder.add_edge("assemble_linked_context", "expand_relational_context")
    builder.add_edge("expand_relational_context", "select_relational_evidence")
    builder.add_edge("select_relational_evidence", "generate_relational_candidate")
    builder.add_edge("generate_relational_candidate", END)
    return builder.compile(checkpointer=InMemorySaver())

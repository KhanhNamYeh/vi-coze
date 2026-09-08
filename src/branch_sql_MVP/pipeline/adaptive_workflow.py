"""Adaptive LangGraph với model-driven route và candidate fan-out/fan-in."""

from __future__ import annotations

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from ..offline.event_index import load_event_index
from ..online.candidate_selection import select_best_candidate
from ..online.context_builder import (
    build_full_context,
    build_linked_context,
    load_optional_example_index,
    select_evidence_bundle,
)
from ..online.llm import (
    decide_workflow_route,
    generate_sql_candidate,
    select_candidate_with_model,
    select_contextual_evidence,
)
from ..online.sag_retrieval import expand_event_neighborhood, retrieve_seed_events
from ..online.sql_execution import execute_readonly_sql
from ..settings import Settings
from .state import WorkflowState

STRATEGIES = ["join_first", "aggregation_first", "literal_first"]


def _render(items: list[dict]) -> str:
    return "\n\n".join(
        f"[{item['kind'].upper()} id={item['id']} source={item['source']}]\n{item['text']}" for item in items
    )


def build_adaptive_workflow(
    settings: Settings,
    *,
    provider: str | None = None,
    model: str | None = None,
    api_key: str | None = None,
):
    def choose_context_route(state: WorkflowState) -> dict:
        decision, trace = decide_workflow_route(
            state["question"],
            state.get("difficulty", "unknown"),
            settings=settings,
            provider=provider,
            model=model,
            api_key=api_key,
        )
        maximum = int(state.get("route_parameters", {}).get("max_candidates", 3))
        count = min(decision.candidate_count, maximum)
        return {
            "route": decision.route,
            "candidate_strategies": STRATEGIES[:count],
            "trajectory": [{"node": "choose_context_route", "route": decision.route, "candidate_count": count, **trace}],
        }

    def route_context(state: WorkflowState) -> str:
        return state["route"]

    def assemble_full_context(state: WorkflowState) -> dict:
        context, items, stats = build_full_context(
            state["question"], state.get("evidence", ""), state["schema_catalog_path"], state["business_path"]
        )
        return {"context_text": context, "evidence_items": items, "trajectory": [{"node": "assemble_full_context", **stats}]}

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
        return {"context_text": context, "evidence_items": items, "trajectory": [{"node": "assemble_linked_context", "trace": trace}]}

    def assemble_relational_context(state: WorkflowState) -> dict:
        linked_update = assemble_linked_context(state)
        linked = linked_update["evidence_items"]
        parameters = state.get("context_parameters", {})
        index = load_event_index(state["event_index_path"])
        seeds = retrieve_seed_events(state["question"], linked, index, top_k=int(parameters.get("event_top_k", 8)))
        events = expand_event_neighborhood(
            seeds,
            index,
            hops=int(parameters.get("event_hops", 1)),
            node_budget=int(parameters.get("event_node_budget", 24)),
            token_budget=int(parameters.get("event_token_budget", 1800)),
        )
        combined = [*linked, *events]
        if parameters.get("contextual_selector", True):
            selected, selector_trace = select_contextual_evidence(
                state["question"],
                combined,
                max_items=int(parameters.get("selector_max_items", 24)),
                settings=settings,
                provider=provider,
                model=model,
                api_key=api_key,
            )
        else:
            selected, budget_trace = select_evidence_bundle(
                combined,
                token_budget=int(parameters.get("token_budget", 5000)),
            )
            selector_trace = {"mode": "deterministic_budget", "items": budget_trace}
        return {
            "context_text": _render(selected),
            "evidence_items": selected,
            "trajectory": [
                *linked_update["trajectory"],
                {"node": "assemble_relational_context", "seed_event_ids": seeds, "event_items": len(events), "selector": selector_trace},
            ],
        }

    def dispatch_candidates(state: WorkflowState):
        return [
            Send(
                "generate_candidate",
                {
                    "stable_id": state["stable_id"],
                    "question": state["question"],
                    "evidence": state.get("evidence", ""),
                    "context_text": state["context_text"],
                    "candidate_strategy": strategy,
                },
            )
            for strategy in state["candidate_strategies"]
        ]

    def generate_candidate(state: WorkflowState) -> dict:
        strategy = state["candidate_strategy"]
        prediction = generate_sql_candidate(
            state["question"],
            state["context_text"],
            strategy=strategy,
            settings=settings,
            provider=provider,
            model=model,
            api_key=api_key,
        ).model_dump(mode="json")
        candidate_id = f"candidate_{STRATEGIES.index(strategy) + 1}"
        return {
            "candidates": [{"candidate_id": candidate_id, "strategy": strategy, "prediction": prediction}],
            "trajectory": [{"node": "generate_candidate", "candidate_id": candidate_id, "strategy": strategy}],
        }

    def execute_candidates(state: WorkflowState) -> dict:
        execution = state.get("execution_parameters", {})
        observations = [
            execute_readonly_sql(
                state["database_path"],
                candidate["prediction"]["sql"],
                timeout_seconds=float(execution.get("timeout_seconds", 5.0)),
                max_rows=int(execution.get("max_rows", 500)),
            ).model_dump(mode="json")
            for candidate in state["candidates"]
        ]
        return {
            "observations": observations,
            "trajectory": [
                {"node": "execute_candidates", "statuses": [item["status"] for item in observations]}
            ],
        }

    def choose_best_candidate(state: WorkflowState) -> dict:
        enriched = [
            {**candidate, "observation": state["observations"][index]}
            for index, candidate in enumerate(state["candidates"])
        ]
        if len(enriched) == 1:
            selected = enriched[0]
            trace = {"reason": "single_candidate"}
        else:
            selected_id, trace = select_candidate_with_model(
                state["question"],
                enriched,
                settings=settings,
                provider=provider,
                model=model,
                api_key=api_key,
            )
            selected = next((item for item in enriched if item["candidate_id"] == selected_id), None)
            selected = selected or select_best_candidate(enriched)
        return {
            "final_prediction": selected["prediction"],
            "trajectory": [{"node": "choose_best_candidate", "selected_candidate_id": selected["candidate_id"], **trace}],
        }

    builder = StateGraph(WorkflowState)
    builder.add_node("choose_context_route", choose_context_route)
    builder.add_node("assemble_full_context", assemble_full_context)
    builder.add_node("assemble_linked_context", assemble_linked_context)
    builder.add_node("assemble_relational_context", assemble_relational_context)
    builder.add_node("generate_candidate", generate_candidate)
    builder.add_node("execute_candidates", execute_candidates)
    builder.add_node("choose_best_candidate", choose_best_candidate)
    builder.add_edge(START, "choose_context_route")
    builder.add_conditional_edges(
        "choose_context_route",
        route_context,
        {
            "full": "assemble_full_context",
            "hybrid": "assemble_linked_context",
            "sag": "assemble_relational_context",
        },
    )
    for context_node in ("assemble_full_context", "assemble_linked_context", "assemble_relational_context"):
        builder.add_conditional_edges(context_node, dispatch_candidates, ["generate_candidate"])
    builder.add_edge("generate_candidate", "execute_candidates")
    builder.add_edge("execute_candidates", "choose_best_candidate")
    builder.add_edge("choose_best_candidate", END)
    return builder.compile(checkpointer=InMemorySaver())

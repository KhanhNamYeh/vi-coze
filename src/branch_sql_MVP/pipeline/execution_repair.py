"""Workflow generate–execute–observe–repair có loop bound và early stop."""

from __future__ import annotations

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from ..offline.event_index import load_event_index
from ..online.candidate_selection import select_best_candidate
from ..online.context_builder import (
    build_linked_context,
    load_optional_example_index,
    select_evidence_bundle,
)
from ..online.llm import generate_sql_candidate, repair_sql_candidate, select_contextual_evidence
from ..online.sag_retrieval import expand_event_neighborhood, retrieve_seed_events
from ..online.sql_execution import execute_readonly_sql
from ..settings import Settings
from .state import WorkflowState


def _render(items: list[dict]) -> str:
    return "\n\n".join(
        f"[{item['kind'].upper()} id={item['id']} source={item['source']}]\n{item['text']}" for item in items
    )


def build_repair_workflow(
    settings: Settings,
    *,
    provider: str | None = None,
    model: str | None = None,
    api_key: str | None = None,
):
    def assemble_frozen_context(state: WorkflowState) -> dict:
        parameters = state.get("context_parameters", {})
        linked_context, linked, retrieval_trace = build_linked_context(
            state["question"],
            state.get("evidence", ""),
            state["schema_catalog_path"],
            knowledge_id=str(parameters["knowledge_id"]),
            doc_id=str(parameters["doc_id"]),
            settings=settings,
            parameters=parameters,
            example_index=load_optional_example_index(parameters.get("example_index_path")),
        )
        if not bool(parameters.get("use_relational_context", True)):
            return {
                "context_text": linked_context,
                "evidence_items": linked,
                "trajectory": [
                    {
                        "node": "assemble_frozen_context",
                        "retrieval_trace": retrieval_trace,
                        "relational_context": False,
                    }
                ],
            }
        index = load_event_index(state["event_index_path"])
        seeds = retrieve_seed_events(
            state["question"], linked, index, top_k=int(parameters.get("event_top_k", 8))
        )
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
                {
                    "node": "assemble_frozen_context",
                    "retrieval_trace": retrieval_trace,
                    "seed_event_ids": seeds,
                    "event_items": len(events),
                    "selector": selector_trace,
                }
            ],
        }

    def generate_initial_candidate(state: WorkflowState) -> dict:
        prediction = generate_sql_candidate(
            state["question"],
            state["context_text"],
            strategy="execution_guided_initial",
            settings=settings,
            provider=provider,
            model=model,
            api_key=api_key,
        ).model_dump(mode="json")
        return {
            "candidates": [
                {"candidate_id": "candidate_0", "strategy": "execution_guided_initial", "prediction": prediction}
            ],
            "repair_count": 0,
            "observations": [],
            "trajectory": [{"node": "generate_initial_candidate", "candidate_id": "candidate_0"}],
        }

    def observe_latest_candidate(state: WorkflowState) -> dict:
        execution = state.get("execution_parameters", {})
        candidate = state["candidates"][-1]
        observation = execute_readonly_sql(
            state["database_path"],
            candidate["prediction"]["sql"],
            timeout_seconds=float(execution.get("timeout_seconds", 5.0)),
            max_rows=int(execution.get("max_rows", 500)),
        ).model_dump(mode="json")
        return {
            "observations": [*state.get("observations", []), observation],
            "trajectory": [
                {
                    "node": "observe_latest_candidate",
                    "candidate_id": candidate["candidate_id"],
                    "status": observation["status"],
                }
            ],
        }

    def decide_after_observation(state: WorkflowState) -> str:
        status = state["observations"][-1]["status"]
        repeated = len(state["candidates"]) > 1 and (
            state["candidates"][-1]["prediction"]["sql"].strip().casefold()
            == state["candidates"][-2]["prediction"]["sql"].strip().casefold()
        )
        if status in {"success", "empty_result"} or repeated:
            return "finalize_candidate"
        if state.get("repair_count", 0) >= state.get("max_repairs", 2):
            return "finalize_candidate"
        return "repair_candidate"

    def repair_candidate(state: WorkflowState) -> dict:
        repair_number = state.get("repair_count", 0) + 1
        prediction = repair_sql_candidate(
            state["question"],
            state["context_text"],
            state["candidates"][-1]["prediction"]["sql"],
            state["observations"][-1],
            settings=settings,
            provider=provider,
            model=model,
            api_key=api_key,
        ).model_dump(mode="json")
        return {
            "candidates": [
                {
                    "candidate_id": f"candidate_{repair_number}",
                    "strategy": "minimal_execution_repair",
                    "prediction": prediction,
                }
            ],
            "repair_count": repair_number,
            "trajectory": [{"node": "repair_candidate", "repair_count": repair_number}],
        }

    def finalize_candidate(state: WorkflowState) -> dict:
        candidates = []
        observations = state.get("observations", [])
        for index, candidate in enumerate(state["candidates"]):
            candidates.append(
                {**candidate, "observation": observations[index] if index < len(observations) else None}
            )
        selected = select_best_candidate(candidates)
        return {
            "final_prediction": selected["prediction"],
            "trajectory": [
                {"node": "finalize_candidate", "selected_candidate_id": selected["candidate_id"]}
            ],
        }

    builder = StateGraph(WorkflowState)
    builder.add_node("assemble_frozen_context", assemble_frozen_context)
    builder.add_node("generate_initial_candidate", generate_initial_candidate)
    builder.add_node("observe_latest_candidate", observe_latest_candidate)
    builder.add_node("repair_candidate", repair_candidate)
    builder.add_node("finalize_candidate", finalize_candidate)
    builder.add_edge(START, "assemble_frozen_context")
    builder.add_edge("assemble_frozen_context", "generate_initial_candidate")
    builder.add_edge("generate_initial_candidate", "observe_latest_candidate")
    builder.add_conditional_edges(
        "observe_latest_candidate",
        decide_after_observation,
        {
            "repair_candidate": "repair_candidate",
            "finalize_candidate": "finalize_candidate",
        },
    )
    builder.add_edge("repair_candidate", "observe_latest_candidate")
    builder.add_edge("finalize_candidate", END)
    return builder.compile(checkpointer=InMemorySaver())

"""Chạy tuần tự dev tuning rồi khóa cấu hình để đánh giá toàn bộ test."""

from __future__ import annotations

import argparse
import hashlib
import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from ..data.catalog import load_benchmark_cases
from ..settings import load_settings
from .benchmark import (
    prepare_benchmark_artifacts,
    run_scenario,
    score_linked_context,
    score_relational_context,
    stratified_sample,
)

RUNTIME_ROOT = Path(__file__).resolve().parents[1].joinpath(".runtime/text2sql_benchmark")
BUNDLE_PATH = RUNTIME_ROOT / "benchmark_bundle.json"
DEV_CASES_PER_DATABASE = 1
MAX_CONCURRENCY = 3
SEED = 42

BASE_CONTEXT: dict[str, Any] = {
    "mode": "hybrid",
    "candidate_k": 8,
    "docs_top_k": 3,
    "semantic_weight": 0.5,
    "keyword_weight": 0.5,
    "rrf_k": 40,
    "rerank_top_k": 4,
    "rerank_enabled": False,
    "rerank_max_length": 128,
    "rerank_batch_size": 8,
    "table_k": 5,
    "column_k": 12,
    "schema_min_score": 0.12,
    "value_k": 8,
    "value_fuzzy_threshold": 0.84,
    "token_budget": 5000,
    "event_top_k": 8,
    "event_hops": 1,
    "event_node_budget": 24,
    "event_token_budget": 1800,
    "selector_max_items": 24,
    "example_k": 0,
}

RETRIEVAL_GRID = [
    {"name": "hybrid_rrf_dense_0_3", "semantic_weight": 0.3, "keyword_weight": 0.7},
    {"name": "hybrid_rrf_balanced", "semantic_weight": 0.5, "keyword_weight": 0.5},
    {"name": "hybrid_rrf_dense_0_7", "semantic_weight": 0.7, "keyword_weight": 0.3},
    {
        "name": "hybrid_crossencoder_128",
        "semantic_weight": 0.5,
        "keyword_weight": 0.5,
        "rerank_enabled": True,
    },
]
SCHEMA_GRID = [
    {"name": "schema_compact", "table_k": 3, "column_k": 8},
    {"name": "schema_balanced", "table_k": 5, "column_k": 12},
    {"name": "schema_wide", "table_k": 8, "column_k": 18},
]
TOKEN_GRID = [
    {"name": "context_3k", "token_budget": 3000},
    {"name": "context_5k", "token_budget": 5000},
    {"name": "context_7k", "token_budget": 7000},
]
EVENT_GRID = [
    {"name": "events_seed_4", "event_top_k": 4, "event_hops": 0},
    {"name": "events_seed_8", "event_top_k": 8, "event_hops": 0},
    {"name": "events_expand_1", "event_top_k": 4, "event_hops": 1},
    {"name": "events_expand_2", "event_top_k": 4, "event_hops": 2},
]
SELECTOR_GRID = [12, 24]
REPAIR_GRID = [0, 1, 2]
CANDIDATE_GRID = [1, 2, 3]
EXECUTION_PARAMETERS = {
    "timeout_seconds": 5.0,
    "max_rows": 500,
    "eval_timeout_seconds": 10.0,
}


def _write_bundle(bundle: dict[str, Any], path: Path = BUNDLE_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(bundle, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _merged(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    return {**base, **{key: value for key, value in patch.items() if key != "name"}}


def _best_context(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return max(
        rows,
        key=lambda row: (
            float(row["schema_complete_rate"]),
            float(row["schema_table_recall"]),
            -float(row.get("mean_context_tokens", 0)),
            -float(row.get("elapsed_seconds", 0)),
        ),
    )


def _best_event(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return max(
        rows,
        key=lambda row: (
            float(row["event_gold_complete_rate"]),
            float(row["event_gold_table_recall"]),
            -float(row["mean_event_items"]),
            -float(row["parameters"]["event_hops"]),
            -float(row["elapsed_seconds"]),
        ),
    )


def _best_generation(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return max(
        rows,
        key=lambda row: (
            float(row["metrics"]["execution_accuracy"]),
            -float(row["metrics"]["invalid_sql_rate"]),
            -float(row["metrics"]["input_tokens_all_calls"]),
        ),
    )


def _config_hash(value: dict[str, Any]) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:10]


def _progress(stage: str):
    def report(done: int, total: int, stable_id: str) -> None:
        print(f"[{stage}] {done}/{total} {stable_id}", flush=True)

    return report


def _scenario_summary(
    cases,
    *,
    label: str,
    scenario: str,
    artifacts: dict[str, Any],
    settings,
    context: dict[str, Any],
    max_repairs: int = 0,
    route: dict[str, Any] | None = None,
) -> dict[str, Any]:
    identity = {
        "label": label,
        "scenario": scenario,
        "context": context,
        "max_repairs": max_repairs,
        "route": route or {},
        "dataset_fingerprint": artifacts["dataset_fingerprint"],
        "index_fingerprint": artifacts["index_fingerprint"],
        "provider": settings.api.provider,
        "model": settings.api.model,
    }
    run_id = f"{cases[0].split}-{label}-{_config_hash(identity)}"
    summary, _ = run_scenario(
        cases,
        scenario=scenario,
        run_id=run_id,
        artifacts=artifacts,
        settings=settings,
        context_parameters=context,
        execution_parameters=EXECUTION_PARAMETERS,
        route_parameters=route,
        max_repairs=max_repairs,
        max_concurrency=MAX_CONCURRENCY,
        resume=True,
        progress=_progress(label),
    )
    return {"label": label, **summary}


def run_all(
    *,
    recreate_artifacts: bool = False,
    stop_after_context: bool = False,
    provider: str | None = None,
    model: str | None = None,
    runtime_root: str | Path = RUNTIME_ROOT,
    bundle_path: str | Path | None = None,
) -> dict[str, Any]:
    base_settings = load_settings()
    api_settings = base_settings.api.model_copy(
        update={
            "provider": provider or base_settings.api.provider,
            "model": model or base_settings.api.model,
        }
    )
    requested_settings = base_settings.model_copy(update={"api": api_settings})
    output_path = Path(bundle_path) if bundle_path else Path(runtime_root) / "benchmark_bundle.json"

    def save(value: dict[str, Any]) -> None:
        _write_bundle(value, output_path)

    settings, artifacts = prepare_benchmark_artifacts(
        settings=requested_settings,
        runtime_root=runtime_root,
        recreate=recreate_artifacts,
    )
    dev = load_benchmark_cases(settings.path(settings.paths.dev), "dev")
    test = load_benchmark_cases(settings.path(settings.paths.test), "test")
    dev_sample = stratified_sample(dev, DEV_CASES_PER_DATABASE, seed=SEED)
    bundle: dict[str, Any] = {
        "protocol": {
            "order": "tune only on dev, freeze parameters, report only on test",
            "dev_total_cases": len(dev),
            "dev_tuning_cases": len(dev_sample),
            "dev_sampling": f"stratified {DEV_CASES_PER_DATABASE} case/database, seed={SEED}",
            "test_cases": len(test),
            "test_scope": "all cases",
            "evaluation": "sqlite_result_equivalence_v1",
            "r_ves": None,
            "example_corpus": artifacts["example_corpus"],
            "provider": settings.api.provider,
            "model": settings.api.model,
        },
        "artifacts": artifacts,
        "parameter_space": {
            "base_context": BASE_CONTEXT,
            "retrieval_grid": RETRIEVAL_GRID,
            "schema_grid": SCHEMA_GRID,
            "token_grid": TOKEN_GRID,
            "event_grid": EVENT_GRID,
            "selector_grid": SELECTOR_GRID,
            "repair_grid": REPAIR_GRID,
            "candidate_grid": CANDIDATE_GRID,
            "execution": EXECUTION_PARAMETERS,
            "dev_cases_per_database": DEV_CASES_PER_DATABASE,
            "max_concurrency": MAX_CONCURRENCY,
            "seed": SEED,
        },
        "dev_stable_ids": [case.stable_id for case in dev_sample],
        "dev_tuning": {},
        "selected": {},
        "test_scenarios": [],
    }
    save(bundle)

    context = deepcopy(BASE_CONTEXT)
    print("[dev] tuning retrieval", flush=True)
    retrieval_rows = []
    for candidate in RETRIEVAL_GRID:
        parameters = _merged(context, candidate)
        metrics = score_linked_context(dev_sample, artifacts, settings, parameters)
        row = {"name": candidate["name"], "parameters": parameters, **metrics}
        retrieval_rows.append(row)
        print(json.dumps(row, ensure_ascii=False), flush=True)
    chosen = _best_context(retrieval_rows)
    context = chosen["parameters"]
    bundle["dev_tuning"]["retrieval"] = retrieval_rows
    bundle["selected"]["retrieval"] = chosen
    save(bundle)

    print("[dev] tuning schema linking", flush=True)
    schema_rows = []
    for candidate in SCHEMA_GRID:
        parameters = _merged(context, candidate)
        metrics = score_linked_context(dev_sample, artifacts, settings, parameters)
        row = {"name": candidate["name"], "parameters": parameters, **metrics}
        schema_rows.append(row)
        print(json.dumps(row, ensure_ascii=False), flush=True)
    chosen = _best_context(schema_rows)
    context = chosen["parameters"]
    bundle["dev_tuning"]["schema"] = schema_rows
    bundle["selected"]["schema"] = chosen
    save(bundle)

    print("[dev] tuning context token budget", flush=True)
    token_rows = []
    for candidate in TOKEN_GRID:
        parameters = _merged(context, candidate)
        metrics = score_linked_context(dev_sample, artifacts, settings, parameters)
        row = {"name": candidate["name"], "parameters": parameters, **metrics}
        token_rows.append(row)
        print(json.dumps(row, ensure_ascii=False), flush=True)
    chosen = _best_context(token_rows)
    context = chosen["parameters"]
    bundle["dev_tuning"]["token_budget"] = token_rows
    bundle["selected"]["token_budget"] = chosen
    save(bundle)

    print("[dev] tuning event expansion", flush=True)
    event_rows = []
    for candidate in EVENT_GRID:
        parameters = _merged(context, candidate)
        metrics = score_relational_context(dev_sample, artifacts, settings, parameters)
        row = {"name": candidate["name"], "parameters": parameters, **metrics}
        event_rows.append(row)
        print(json.dumps(row, ensure_ascii=False), flush=True)
    chosen = _best_event(event_rows)
    context = chosen["parameters"]
    bundle["dev_tuning"]["events"] = event_rows
    bundle["selected"]["events"] = chosen
    bundle["selected"]["frozen_context"] = context
    save(bundle)

    if stop_after_context:
        print("[dev] stopped after local context tuning as requested", flush=True)
        return bundle

    print("[dev] tuning contextual selector", flush=True)
    selector_rows = []
    for maximum in SELECTOR_GRID:
        parameters = {**context, "selector_max_items": maximum, "contextual_selector": True}
        summary = _scenario_summary(
            dev_sample,
            label=f"selector-{maximum}",
            scenario="B5",
            artifacts=artifacts,
            settings=settings,
            context=parameters,
        )
        selector_rows.append({"value": maximum, **summary})
        save({**bundle, "dev_tuning": {**bundle["dev_tuning"], "selector": selector_rows}})
    chosen = _best_generation(selector_rows)
    context = {**context, "selector_max_items": chosen["value"], "contextual_selector": True}
    bundle["dev_tuning"]["selector"] = selector_rows
    bundle["selected"]["selector"] = chosen
    save(bundle)

    print("[dev] tuning repair bound", flush=True)
    repair_rows = []
    for repairs in REPAIR_GRID:
        summary = _scenario_summary(
            dev_sample,
            label=f"repair-{repairs}",
            scenario="B6",
            artifacts=artifacts,
            settings=settings,
            context=context,
            max_repairs=repairs,
        )
        repair_rows.append({"value": repairs, **summary})
        save({**bundle, "dev_tuning": {**bundle["dev_tuning"], "repair": repair_rows}})
    chosen = _best_generation(repair_rows)
    max_repairs = int(chosen["value"])
    bundle["dev_tuning"]["repair"] = repair_rows
    bundle["selected"]["repair"] = chosen
    save(bundle)

    print("[dev] tuning adaptive candidate bound", flush=True)
    candidate_rows = []
    for maximum in CANDIDATE_GRID:
        summary = _scenario_summary(
            dev_sample,
            label=f"adaptive-candidates-{maximum}",
            scenario="G1",
            artifacts=artifacts,
            settings=settings,
            context=context,
            route={"max_candidates": maximum},
        )
        candidate_rows.append({"value": maximum, **summary})
        save({**bundle, "dev_tuning": {**bundle["dev_tuning"], "candidates": candidate_rows}})
    chosen = _best_generation(candidate_rows)
    max_candidates = int(chosen["value"])
    bundle["dev_tuning"]["candidates"] = candidate_rows
    bundle["selected"]["candidates"] = chosen
    bundle["selected"]["frozen_context"] = context
    save(bundle)

    test_specs = [
        {"label": "P1-full-one-shot", "scenario": "P1", "context": {}},
        {"label": "B4-hybrid-fixed", "scenario": "B4", "context": context},
        {
            "label": "B4-plus-event-seeds",
            "scenario": "B5",
            "context": {**context, "use_events": True, "expand_events": False, "contextual_selector": False},
        },
        {
            "label": "B4-plus-event-expansion",
            "scenario": "B5",
            "context": {**context, "use_events": True, "expand_events": True, "contextual_selector": False},
        },
        {"label": "B5-relational-selector", "scenario": "B5", "context": context},
        {
            "label": "B6-repair-relational",
            "scenario": "B6",
            "context": {**context, "use_relational_context": True},
            "max_repairs": max_repairs,
        },
        {
            "label": "B6-repair-hybrid",
            "scenario": "B6",
            "context": {**context, "use_relational_context": False},
            "max_repairs": max_repairs,
        },
        {
            "label": "G1-adaptive",
            "scenario": "G1",
            "context": context,
            "route": {"max_candidates": max_candidates},
        },
    ]
    print("[test] parameters frozen; starting all scenarios", flush=True)
    completed_labels = {row["label"] for row in bundle["test_scenarios"]}
    for spec in test_specs:
        if spec["label"] in completed_labels:
            continue
        summary = _scenario_summary(
            test,
            label=spec["label"],
            scenario=spec["scenario"],
            artifacts=artifacts,
            settings=settings,
            context=spec["context"],
            max_repairs=int(spec.get("max_repairs", 0)),
            route=spec.get("route"),
        )
        bundle["test_scenarios"].append({"spec": spec, **summary})
        save(bundle)
    return bundle


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--recreate-artifacts", action="store_true")
    parser.add_argument("--stop-after-context", action="store_true")
    parser.add_argument("--provider")
    parser.add_argument("--model")
    parser.add_argument("--runtime-root", default=str(RUNTIME_ROOT))
    parser.add_argument("--bundle-path")
    args = parser.parse_args()
    bundle = run_all(
        recreate_artifacts=args.recreate_artifacts,
        stop_after_context=args.stop_after_context,
        provider=args.provider,
        model=args.model,
        runtime_root=args.runtime_root,
        bundle_path=args.bundle_path,
    )
    output_path = Path(args.bundle_path) if args.bundle_path else Path(args.runtime_root) / "benchmark_bundle.json"
    print(f"Đã lưu bundle: {output_path.resolve()}")
    print(json.dumps([row["metrics"] for row in bundle["test_scenarios"]], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

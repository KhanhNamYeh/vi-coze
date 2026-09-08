"""Tune từng tầng end-to-end trên dev rồi đánh giá Luna trên toàn bộ test."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
from collections.abc import Callable
from copy import deepcopy
from pathlib import Path
from typing import Any

os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")

from ..data.catalog import BenchmarkCase, load_benchmark_cases
from ..online import token_budget
from ..settings import Settings, load_settings
from .benchmark import (
    prepare_benchmark_artifacts,
    run_scenario,
    score_linked_context,
    score_relational_context,
)
from .dataset_split import split_cases

RUNTIME_ROOT = Path(__file__).resolve().parents[1].joinpath(".runtime/luna_internal_holdout_v1")
BUNDLE_PATH = RUNTIME_ROOT / "luna_component_tuning.json"
MODEL_PROVIDER = "openai"
MODEL_NAME = "gpt-5.6-luna"
WORKFLOW_REVISION = "internal-holdout-v1"
SEED = 42
MAX_CONCURRENCY = 6
EXECUTION_PARAMETERS = {
    "timeout_seconds": 5.0,
    "max_rows": 500,
    "eval_timeout_seconds": 10.0,
}

BASE_CONTEXT: dict[str, Any] = {
    "mode": "hybrid",
    "candidate_k": 16,
    "docs_top_k": 5,
    "semantic_weight": 0.5,
    "keyword_weight": 0.5,
    "rrf_k": 40,
    "rerank_top_k": 5,
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

REASONING_GRID = ["low", "medium", "high"]
CONTEXT_STAGES: list[dict[str, Any]] = [
    {
        "name": "retrieval_fusion",
        "scenario": "B4",
        "proxy": "linked",
        "candidates": [
            {"name": "dense_only", "mode": "semantic", "semantic_weight": 1.0, "keyword_weight": 0.0},
            {"name": "keyword_only", "mode": "keyword", "semantic_weight": 0.0, "keyword_weight": 1.0},
            {"name": "hybrid_keyword_0_7", "mode": "hybrid", "semantic_weight": 0.3, "keyword_weight": 0.7},
            {"name": "hybrid_balanced", "mode": "hybrid", "semantic_weight": 0.5, "keyword_weight": 0.5},
            {"name": "hybrid_dense_0_7", "mode": "hybrid", "semantic_weight": 0.7, "keyword_weight": 0.3},
        ],
    },
    {
        "name": "reranking",
        "scenario": "B4",
        "proxy": "linked",
        "candidates": [
            {"name": "rerank_off", "rerank_enabled": False},
            {"name": "rerank_top4_128", "rerank_enabled": True, "rerank_top_k": 4, "rerank_max_length": 128},
            {"name": "rerank_top8_128", "rerank_enabled": True, "rerank_top_k": 8, "rerank_max_length": 128},
            {"name": "rerank_top8_256", "rerank_enabled": True, "rerank_top_k": 8, "rerank_max_length": 256},
        ],
    },
    {
        "name": "retrieval_depth",
        "scenario": "B4",
        "proxy": "linked",
        "candidates": [
            {"name": "depth_3", "candidate_k": 8, "docs_top_k": 3, "rerank_top_k": 3},
            {"name": "depth_5", "candidate_k": 16, "docs_top_k": 5, "rerank_top_k": 5},
            {"name": "depth_8", "candidate_k": 24, "docs_top_k": 8, "rerank_top_k": 8},
        ],
    },
    {
        "name": "schema_linking",
        "scenario": "B4",
        "proxy": "linked",
        "candidates": [
            {"name": "schema_compact", "table_k": 3, "column_k": 8},
            {"name": "schema_balanced", "table_k": 5, "column_k": 12},
            {"name": "schema_wide", "table_k": 8, "column_k": 20},
            {"name": "schema_max", "table_k": 12, "column_k": 32},
        ],
    },
    {
        "name": "value_linking",
        "scenario": "B4",
        "proxy": "linked",
        "candidates": [
            {"name": "values_off", "value_k": 0, "value_fuzzy_threshold": 1.0},
            {"name": "values_strict", "value_k": 4, "value_fuzzy_threshold": 0.92},
            {"name": "values_balanced", "value_k": 8, "value_fuzzy_threshold": 0.84},
            {"name": "values_recall", "value_k": 16, "value_fuzzy_threshold": 0.70},
        ],
    },
    {
        "name": "context_budget",
        "scenario": "B4",
        "proxy": "linked",
        "candidates": [
            {"name": "context_2k", "token_budget": 2000},
            {"name": "context_3k", "token_budget": 3000},
            {"name": "context_5k", "token_budget": 5000},
            {"name": "context_8k", "token_budget": 8000},
            {"name": "context_12k", "token_budget": 12000},
        ],
    },
    {
        "name": "event_expansion",
        "scenario": "B5",
        "proxy": "relational",
        "base_patch": {"use_events": True, "expand_events": True, "contextual_selector": False},
        "candidates": [
            {"name": "events_off", "use_events": False, "event_top_k": 0, "event_hops": 0},
            {"name": "events_seed_4", "event_top_k": 4, "event_hops": 0},
            {"name": "events_seed_8", "event_top_k": 8, "event_hops": 0},
            {"name": "events_expand_4x1", "event_top_k": 4, "event_hops": 1},
            {"name": "events_expand_8x1", "event_top_k": 8, "event_hops": 1},
            {"name": "events_expand_8x2", "event_top_k": 8, "event_hops": 2},
            {"name": "events_expand_12x2", "event_top_k": 12, "event_hops": 2},
        ],
    },
    {
        "name": "contextual_selector",
        "scenario": "B5",
        "proxy": "relational",
        "base_patch": {"use_events": True, "expand_events": True, "contextual_selector": True},
        "candidates": [
            {"name": "selector_off", "contextual_selector": False},
            {"name": "selector_8", "selector_max_items": 8},
            {"name": "selector_12", "selector_max_items": 12},
            {"name": "selector_24", "selector_max_items": 24},
            {"name": "selector_40", "selector_max_items": 40},
        ],
    },
]
REPAIR_GRID = [0, 1, 2, 3]
CANDIDATE_GRID = [1, 2, 3]
_PROXY_CACHE: dict[str, dict[str, Any]] = {}


def difficulty_balanced_sample(
    cases: list[BenchmarkCase],
    *,
    per_database_difficulty: int = 1,
    seed: int = SEED,
) -> list[BenchmarkCase]:
    """Lấy cùng số case simple/moderate/challenging cho từng database."""
    grouped: dict[tuple[str, str], list[BenchmarkCase]] = {}
    for case in cases:
        grouped.setdefault((case.db_id, case.difficulty), []).append(case)
    randomizer = random.Random(seed)
    selected: list[BenchmarkCase] = []
    databases = sorted({case.db_id for case in cases})
    difficulties = ("simple", "moderate", "challenging")
    for database in databases:
        for difficulty in difficulties:
            pool = sorted(grouped.get((database, difficulty), []), key=lambda case: case.stable_id)
            randomizer.shuffle(pool)
            selected.extend(pool[:per_database_difficulty])
    return sorted(selected, key=lambda case: case.stable_id)


def _hash(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]


def _write_bundle(bundle: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(bundle, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _merge(base: dict[str, Any], *patches: dict[str, Any]) -> dict[str, Any]:
    output = dict(base)
    for patch in patches:
        output.update({key: value for key, value in patch.items() if key != "name"})
    return output


def _settings_with_reasoning(settings: Settings, effort: str) -> Settings:
    extra = {**settings.llm.extra, "reasoning_effort": effort}
    return settings.model_copy(update={"llm": settings.llm.model_copy(update={"extra": extra})})


def _best(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return max(
        rows,
        key=lambda row: (
            float(row["metrics"]["execution_accuracy"]),
            -float(row["metrics"]["run_error_rate"]),
            -float(row["metrics"]["invalid_sql_rate"]),
            -float(row["metrics"]["input_tokens_all_calls"]),
            -float(row["metrics"]["output_tokens_all_calls"]),
        ),
    )


def _run(
    cases: list[BenchmarkCase],
    *,
    label: str,
    scenario: str,
    artifacts: dict[str, Any],
    settings: Settings,
    context: dict[str, Any],
    max_repairs: int = 0,
    route: dict[str, Any] | None = None,
) -> dict[str, Any]:
    identity = {
        "scenario": scenario,
        "context": context,
        "max_repairs": max_repairs,
        "route": route or {},
        "provider": settings.api.provider,
        "model": settings.api.model,
        "llm": settings.llm.model_dump(mode="json"),
        "case_ids": [case.stable_id for case in cases],
        "dataset_fingerprint": artifacts["dataset_fingerprint"],
        "index_fingerprint": artifacts["index_fingerprint"],
    }
    identity["workflow_revision"] = WORKFLOW_REVISION
    identity["execution"] = EXECUTION_PARAMETERS
    run_id = f"{cases[0].split}-{scenario}-{_hash(identity)}"

    def progress(done: int, total: int, stable_id: str) -> None:
        print(f"[{label}] {done}/{total} {stable_id}", flush=True)

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
        progress=progress,
    )
    return {"label": label, **summary}


def _proxy(
    kind: str,
    cases: list[BenchmarkCase],
    artifacts: dict[str, Any],
    settings: Settings,
    context: dict[str, Any],
) -> dict[str, Any]:
    key = _hash({"kind": kind, "parameters": context})
    if key in _PROXY_CACHE:
        return {**_PROXY_CACHE[key], "cache_hit": True}
    scorers: dict[str, Callable[..., dict[str, Any]]] = {
        "linked": score_linked_context,
        "relational": score_relational_context,
    }
    result = scorers[kind](cases, artifacts, settings, context)
    _PROXY_CACHE[key] = result
    return result


def run_all(
    *,
    runtime_root: str | Path = RUNTIME_ROOT,
    bundle_path: str | Path = BUNDLE_PATH,
    recreate_artifacts: bool = False,
    dev_per_stratum: int = 3,
    token_limit: int = 9_000_000,
) -> dict[str, Any]:
    output_path = Path(bundle_path)
    token_budget.active_budget = token_budget.TokenBudget(Path(runtime_root) / "token_ledger.jsonl", token_limit)
    base = load_settings()
    api = base.api.model_copy(update={"provider": MODEL_PROVIDER, "model": MODEL_NAME, "retries": 0, "timeout": 120})
    requested = base.model_copy(update={"api": api, "llm": base.llm.model_copy(update={"max_tokens": 8192})})
    settings, artifacts = prepare_benchmark_artifacts(
        settings=requested,
        runtime_root=runtime_root,
        recreate=recreate_artifacts,
    )
    dev_all = load_benchmark_cases(settings.path(settings.paths.dev), "dev")
    legacy = load_benchmark_cases(settings.path(settings.paths.test), "test")
    dev_pool, test = split_cases(dev_all, legacy)
    dev = difficulty_balanced_sample(dev_pool, per_database_difficulty=dev_per_stratum) if dev_per_stratum else dev_pool
    _PROXY_CACHE.clear()
    if output_path.exists():
        previous = json.loads(output_path.read_text(encoding="utf-8"))
        if (previous.get("dev_stable_ids") == [case.stable_id for case in dev]
                and previous.get("artifacts", {}).get("dataset_fingerprint") == artifacts["dataset_fingerprint"]
                and previous.get("artifacts", {}).get("index_fingerprint") == artifacts["index_fingerprint"]
                and previous.get("protocol", {}).get("workflow_revision") == WORKFLOW_REVISION):
            for stage in CONTEXT_STAGES:
                for row in previous.get("dev_tuning", {}).get(stage["name"], []):
                    if "proxy_metrics" in row and "parameters" in row:
                        key = _hash({"kind": stage["proxy"], "parameters": row["parameters"]})
                        _PROXY_CACHE[key] = row["proxy_metrics"]
    bundle: dict[str, Any] = {
        "protocol": {
            "order": "coordinate search on dev only, freeze once, evaluate all test scenarios",
            "selection_metric_order": [
                "execution_accuracy:max",
                "run_error_rate:min",
                "invalid_sql_rate:min",
                "input_tokens_all_calls:min",
                "output_tokens_all_calls:min",
            ],
            "dev_total_cases": len(dev_all),
            "dev_tuning_cases": len(dev),
            "dev_sampling": f"up to {dev_per_stratum} per database/difficulty; 0 means all",
            "dev_pool_cases": len(dev_pool),
            "split_manifest": "src/eval/dataset_split.json",
            "test_cases": len(test),
            "test_scope": "all internal holdout cases; source IDs retain dev prefix; legacy 62 excluded",
            "provider": settings.api.provider,
            "model": settings.api.model,
            "reasoning_effort": "selected on dev",
            "workflow_revision": WORKFLOW_REVISION,
            "temperature": settings.llm.temperature,
            "evaluation": "sqlite_result_equivalence_v1",
            "r_ves": None,
            "token_limit": token_limit,
            "token_ledger": str(Path(runtime_root) / "token_ledger.jsonl"),
        },
        "artifacts": artifacts,
        "parameter_space": {
            "base_context": BASE_CONTEXT,
            "reasoning_grid": REASONING_GRID,
            "context_stages": CONTEXT_STAGES,
            "repair_grid": REPAIR_GRID,
            "candidate_grid": CANDIDATE_GRID,
            "execution": EXECUTION_PARAMETERS,
            "max_concurrency": MAX_CONCURRENCY,
            "seed": SEED,
        },
        "dev_stable_ids": [case.stable_id for case in dev],
        "dev_tuning": {},
        "selected": {},
        "test_scenarios": [],
    }
    _write_bundle(bundle, output_path)

    reasoning_rows = []
    for effort in REASONING_GRID:
        candidate_settings = _settings_with_reasoning(settings, effort)
        summary = _run(
            dev,
            label=f"component-reasoning-{effort}",
            scenario="P1",
            artifacts=artifacts,
            settings=candidate_settings,
            context={},
        )
        reasoning_rows.append({"value": effort, **summary})
        bundle["dev_tuning"]["reasoning_effort"] = reasoning_rows
        _write_bundle(bundle, output_path)
    reasoning_winner = _best(reasoning_rows)
    settings = _settings_with_reasoning(settings, str(reasoning_winner["value"]))
    bundle["selected"]["reasoning_effort"] = reasoning_winner
    _write_bundle(bundle, output_path)

    context = deepcopy(BASE_CONTEXT)
    incumbent: dict[str, Any] | None = None
    incumbent_scenario: str | None = None
    for stage in CONTEXT_STAGES:
        rows = []
        base_patch = stage.get("base_patch", {})
        for candidate in stage["candidates"]:
            parameters = _merge(context, base_patch, candidate)
            proxy_metrics = _proxy(stage["proxy"], dev, artifacts, settings, parameters)
            summary = _run(
                dev,
                label=f"component-{stage['name']}-{candidate['name']}",
                scenario=stage["scenario"],
                artifacts=artifacts,
                settings=settings,
                context=parameters,
            )
            rows.append(
                {
                    "name": candidate["name"],
                    "patch": {key: value for key, value in candidate.items() if key != "name"},
                    "parameters": parameters,
                    "proxy_metrics": proxy_metrics,
                    **summary,
                }
            )
            bundle["dev_tuning"][stage["name"]] = rows
            _write_bundle(bundle, output_path)
        if incumbent is not None and incumbent_scenario == stage["scenario"]:
            control = deepcopy(incumbent)
            control.update(
                {
                    "name": f"incumbent_before_{stage['name']}",
                    "patch": {},
                    "parameters": context,
                    "proxy_metrics": _proxy(stage["proxy"], dev, artifacts, settings, context),
                    "reused_as_no_change_control": True,
                }
            )
            rows.insert(0, control)
        winner = _best(rows)
        context = winner["parameters"]
        incumbent = winner
        incumbent_scenario = stage["scenario"]
        bundle["selected"][stage["name"]] = winner
        bundle["selected"]["frozen_context"] = context
        _write_bundle(bundle, output_path)

    selector_rows = [row for row in bundle["dev_tuning"]["contextual_selector"] if row["parameters"].get("contextual_selector")]
    full_context = _best(selector_rows)["parameters"]
    bundle["selected"]["full_relational_context"] = full_context
    repair_rows = []
    for maximum in REPAIR_GRID:
        summary = _run(
            dev,
            label=f"component-repair-{maximum}",
            scenario="B6",
            artifacts=artifacts,
            settings=settings,
            context={**full_context, "use_relational_context": True},
            max_repairs=maximum,
        )
        repair_rows.append({"value": maximum, **summary})
        bundle["dev_tuning"]["repair_bound"] = repair_rows
        _write_bundle(bundle, output_path)
    repair_winner = _best(repair_rows)
    max_repairs = int(repair_winner["value"])
    bundle["selected"]["repair_bound"] = repair_winner
    _write_bundle(bundle, output_path)

    candidate_rows = []
    for maximum in CANDIDATE_GRID:
        summary = _run(
            dev,
            label=f"component-candidates-{maximum}",
            scenario="G1",
            artifacts=artifacts,
            settings=settings,
            context=context,
            route={"max_candidates": maximum},
        )
        candidate_rows.append({"value": maximum, **summary})
        bundle["dev_tuning"]["candidate_bound"] = candidate_rows
        _write_bundle(bundle, output_path)
    candidate_winner = _best(candidate_rows)
    max_candidates = int(candidate_winner["value"])
    bundle["selected"]["candidate_bound"] = candidate_winner
    bundle["selected"]["frozen_context"] = context
    _write_bundle(bundle, output_path)

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
        {"label": "B5-relational-selector", "scenario": "B5", "context": full_context},
        {
            "label": "B6-repair-relational",
            "scenario": "B6",
            "context": {**full_context, "use_relational_context": True},
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
    print("[test] cấu hình Luna đã khóa; bắt đầu toàn bộ kịch bản", flush=True)
    for spec in test_specs:
        summary = _run(
            test,
            label=f"optimized-luna-{spec['label']}",
            scenario=spec["scenario"],
            artifacts=artifacts,
            settings=settings,
            context=spec["context"],
            max_repairs=int(spec.get("max_repairs", 0)),
            route=spec.get("route"),
        )
        bundle["test_scenarios"].append({"spec": spec, **summary})
        _write_bundle(bundle, output_path)
    return bundle


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-root", default=str(RUNTIME_ROOT))
    parser.add_argument("--bundle-path", default=str(BUNDLE_PATH))
    parser.add_argument("--recreate-artifacts", action="store_true")
    parser.add_argument("--dev-per-stratum", type=int, default=3, help="Số câu mỗi DB/độ khó; 0 chạy toàn dev")
    parser.add_argument("--token-limit", type=int, default=9_000_000)
    args = parser.parse_args()
    bundle = run_all(
        runtime_root=args.runtime_root,
        bundle_path=args.bundle_path,
        recreate_artifacts=args.recreate_artifacts,
        dev_per_stratum=args.dev_per_stratum,
        token_limit=args.token_limit,
    )
    print(f"Đã lưu bundle: {Path(args.bundle_path).resolve()}")
    print(json.dumps([row["metrics"] for row in bundle["test_scenarios"]], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

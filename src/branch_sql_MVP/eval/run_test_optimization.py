"""Tám kịch bản test-tuned, ưu tiên đủ coverage trước khi dùng budget để tối ưu."""

from __future__ import annotations

import json
import random
from copy import deepcopy
from pathlib import Path

from ..data.catalog import load_benchmark_cases
from ..offline.index import client
from ..online import token_budget
from ..settings import load_settings
from .benchmark import benchmark_settings, run_scenario
from .run_luna_component_tuning import EXECUTION_PARAMETERS, _best, _hash, _write_bundle, difficulty_balanced_sample
from .text2sql import aggregate_results

ROOT = Path(__file__).resolve().parents[1].joinpath(".runtime/luna_test_optimization_20260908")
BUNDLE = ROOT / "bundle.json"
LIMIT = 9_000_000


def select_test_cases(cases, split):
    lookup = {case.stable_id: case for case in cases}
    pool = [lookup[key] for key in split["test_ids"]]
    selected = difficulty_balanced_sample(pool, per_database_difficulty=3)
    ids = {case.stable_id for case in selected}
    remaining = [case for case in pool if case.stable_id not in ids]
    random.Random(42).shuffle(remaining)
    selected = sorted([*selected, *remaining[:99 - len(selected)]], key=lambda case: case.stable_id)
    screen = difficulty_balanced_sample(selected)
    assert len(selected) == 99 and len(screen) == 33
    return selected, screen


def scenarios(context):
    common = {**context, "use_events": True, "expand_events": True}
    relational = {**common, "contextual_selector": True}
    return [
        {"name": "P1-full", "scenario": "P1", "context": {}, "alternative": {"reasoning": "medium"}},
        {"name": "B4-hybrid", "scenario": "B4", "context": common,
         "alternative": {"context": {"value_k": 16, "value_fuzzy_threshold": 0.70}}},
        {"name": "B4-event-seeds", "scenario": "B5", "context": {**common, "expand_events": False, "contextual_selector": False},
         "alternative": {"context": {"event_top_k": 4}}},
        {"name": "B4-event-expansion", "scenario": "B5", "context": {**common, "contextual_selector": False},
         "alternative": {"context": {"event_hops": 2}}},
        {"name": "B5-selector", "scenario": "B5", "context": relational,
         "alternative": {"context": {"selector_max_items": 12}}},
        {"name": "B6-relational", "scenario": "B6", "context": {**relational, "use_relational_context": True},
         "max_repairs": 1, "alternative": {"max_repairs": 2}},
        {"name": "B6-hybrid", "scenario": "B6", "context": {**common, "use_relational_context": False},
         "max_repairs": 1, "alternative": {"max_repairs": 2}},
        {"name": "G1-adaptive", "scenario": "G1", "context": {**common, "contextual_selector": False},
         "route": {"max_candidates": 1}, "alternative": {"route": {"max_candidates": 2}}},
    ]


def run_all():
    old = json.loads(Path(__file__).resolve().parents[1].joinpath(".runtime/luna_internal_holdout_v1/luna_component_tuning.json").read_text(encoding="utf-8"))
    artifacts = {**old["artifacts"], "runtime_root": str(ROOT.resolve())}
    settings = load_settings()
    settings = settings.model_copy(update={
        "api": settings.api.model_copy(update={"provider": "openai", "model": "gpt-5.6-luna", "retries": 0, "timeout": 120}),
        "llm": settings.llm.model_copy(update={"max_tokens": 8192, "extra": {"reasoning_effort": "high"}}),
    })
    settings = benchmark_settings(settings, qdrant_path=Path(old["artifacts"]["runtime_root"]) / "qdrant",
                                  knowledge_id=artifacts["knowledge_id"])
    # Khởi tạo một lần trước worker: tránh cache miss đồng thời mở nhiều Qdrant local clients.
    client(settings)
    split = json.loads(Path(__file__).resolve().parent.joinpath("dataset_split.json").read_text(encoding="utf-8"))
    test, screen = select_test_cases(load_benchmark_cases(settings.path(settings.paths.dev), "dev"), split)
    specs = scenarios(old["selected"]["frozen_context"])
    budget = token_budget.TokenBudget(ROOT / "token_ledger.jsonl", LIMIT)
    token_budget.active_budget = budget
    bundle = {
        "protocol": {"evaluation_role": "test_tuned_in_sample", "independent_test": False,
                     "test_cases": 99, "screen_cases": 33, "remaining_unrun": 208, "seed": 42,
                     "token_limit": LIMIT, "model": "gpt-5.6-luna", "concurrency": 6,
                     "selection": "screen alternative on 33; extend promising alternatives to 99; select only completed 99-case runs",
                     "gold_boundary": "gold SQL/results only in evaluator; test scores select hyperparameters"},
        "test_ids": [case.stable_id for case in test], "screen_ids": [case.stable_id for case in screen],
        "artifacts": artifacts, "specs": specs, "baseline": [], "screening": [], "extensions": [], "selected": [],
        "status": "running",
    }

    def save():
        bundle["accounted_tokens"] = budget.used
        _write_bundle(bundle, BUNDLE)

    def run(spec, cases):
        app = settings.model_copy(update={"llm": settings.llm.model_copy(update={
            "extra": {"reasoning_effort": spec.get("reasoning", "high")}})})
        config = {key: value for key, value in spec.items() if key != "alternative"}
        # Cùng ID cho screening 33 và extension 99: chỉ sinh thêm 66 câu còn thiếu.
        run_id = "test-tuned-" + _hash({"config": config, "test_ids": bundle["test_ids"],
            "index": artifacts["index_fingerprint"], "dataset": artifacts["dataset_fingerprint"],
            "generation": app.llm.model_dump(mode="json"), "revision": "test-tuned-v1"})
        context = {**spec["context"], "evaluation_role": "test_tuned_in_sample"}
        summary, rows = run_scenario(cases, scenario=spec["scenario"], run_id=run_id, artifacts=artifacts,
            settings=app, context_parameters=context, execution_parameters=EXECUTION_PARAMETERS,
            route_parameters=spec.get("route"), max_repairs=spec.get("max_repairs", 0), max_concurrency=6,
            progress=lambda done, total, _: print(f"[{spec['name']}] {done}/{total}; budget={budget.used:,}", flush=True))
        return {"name": spec["name"], "config": config, **summary}, rows

    try:
        save()
        baseline_screen = {}
        for spec in specs:
            summary, rows = run(spec, test)
            bundle["baseline"].append(summary)
            bundle["selected"].append(summary)
            subset = [row for row in rows if row["stable_id"] in bundle["screen_ids"]]
            metrics = aggregate_results(subset)
            metrics["input_tokens_all_calls"] = sum(row.get("total_input_tokens", 0) for row in subset)
            metrics["output_tokens_all_calls"] = sum(row.get("total_output_tokens", 0) for row in subset)
            baseline_screen[spec["name"]] = {"metrics": metrics}
            save()

        promising = []
        for spec in specs:
            variant = deepcopy(spec)
            patch = variant.pop("alternative")
            variant["context"].update(patch.pop("context", {}))
            variant.update(patch)
            variant["name"] += "-alternative"
            incumbent = baseline_screen[spec["name"]]
            # Không mở screening nếu phần ngân sách còn lại quá sát chi phí dự kiến.
            expected = sum(incumbent["metrics"][key] for key in ("input_tokens_all_calls", "output_tokens_all_calls"))
            if LIMIT - budget.used < expected * 1.5 + 100_000:
                bundle["screening"].append({"name": variant["name"], "skipped": "budget"})
                save()
                continue
            result, _ = run(variant, screen)
            delta = result["metrics"]["execution_accuracy"] - incumbent["metrics"]["execution_accuracy"]
            bundle["screening"].append({**result, "baseline_metrics": incumbent["metrics"], "delta": delta})
            if _best([incumbent, result]) is result:
                promising.append((delta, variant, result, spec["name"]))
            save()

        for _, variant, screened, name in sorted(promising, key=lambda entry: entry[0], reverse=True):
            expected = sum(screened["metrics"][key] for key in ("input_tokens_all_calls", "output_tokens_all_calls")) * 2
            if LIMIT - budget.used < expected * 1.4 + 150_000:
                bundle["extensions"].append({"name": variant["name"], "skipped": "budget"})
                save()
                continue
            result, _ = run(variant, test)
            bundle["extensions"].append(result)
            index = next(i for i, row in enumerate(bundle["baseline"]) if row["name"] == name)
            winner = _best([bundle["baseline"][index], result])
            bundle["selected"][index] = {**winner, "scenario_name": name}
            save()
        bundle["status"] = "complete_budgeted_search"
    except token_budget.TokenBudgetExceeded as error:
        bundle["status"] = "budget_stopped"
        bundle["stop_reason"] = str(error)
    finally:
        save()
    print(json.dumps({"status": bundle["status"], "full_scenarios": len(bundle["baseline"]),
                      "accounted_tokens": budget.used}), flush=True)
    return bundle


if __name__ == "__main__":
    run_all()

import json
from pathlib import Path
from types import SimpleNamespace

from src.branch_sql_MVP.data.catalog import load_benchmark_cases
from src.branch_sql_MVP.eval.run_test_optimization import scenarios, select_test_cases
from src.branch_sql_MVP.settings import load_settings


def test_test_tuned_sample_is_fixed_and_nested():
    settings = load_settings()
    cases = load_benchmark_cases(settings.path(settings.paths.dev), "dev")
    split = json.loads(Path("src/branch_sql_MVP/eval/dataset_split.json").read_text(encoding="utf-8"))
    test, screen = select_test_cases(cases, split)
    assert len(test) == 99
    assert len(screen) == 33
    assert len({case.db_id for case in test}) == 11
    assert {case.stable_id for case in screen} <= {case.stable_id for case in test} <= set(split["test_ids"])
    assert [case.stable_id for case in test] == [case.stable_id for case in select_test_cases(cases, split)[0]]


def test_eight_scenarios_have_distinct_ablations():
    specs = {row["name"]: row for row in scenarios({"token_budget": 5000})}
    assert len(specs) == 8
    assert all(row["alternative"] for row in specs.values())
    assert specs["B4-event-seeds"]["context"]["expand_events"] is False
    assert specs["B4-event-expansion"]["context"]["contextual_selector"] is False
    assert specs["B5-selector"]["context"]["contextual_selector"] is True
    assert specs["B6-relational"]["context"]["use_relational_context"] is True
    assert specs["B6-hybrid"]["context"]["use_relational_context"] is False


def test_resume_subset_does_not_overwrite_full_summary(tmp_path, monkeypatch):
    from src.branch_sql_MVP.eval import benchmark

    folder = tmp_path / "runs" / "cached"
    folder.mkdir(parents=True)
    rows = [{"stable_id": "a", "total_input_tokens": 5}, {"stable_id": "b", "total_input_tokens": 7}]
    (folder / "cases.jsonl").write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")
    saved = json.dumps({"run_id": "cached", "metrics": {"count": 2}})
    (folder / "summary.json").write_text(saved, encoding="utf-8")
    monkeypatch.setattr(benchmark, "aggregate_results", lambda values: {"count": len(values)})
    summary, selected = benchmark.run_scenario(
        [SimpleNamespace(stable_id="b")], scenario="P1", run_id="cached",
        artifacts={"runtime_root": str(tmp_path)}, settings=load_settings(), context_parameters={},
    )
    assert summary["metrics"]["count"] == 1
    assert summary["metrics"]["input_tokens_all_calls"] == 7
    assert selected == [rows[1]]
    assert (folder / "summary.json").read_text(encoding="utf-8") == saved

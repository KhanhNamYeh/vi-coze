from types import SimpleNamespace

from src.branch_sql_MVP.eval.run_luna_component_tuning import _best, difficulty_balanced_sample


def test_proxy_reuses_same_configuration_without_retrieval(monkeypatch):
    from src.branch_sql_MVP.eval import run_luna_component_tuning as runner
    calls = []
    monkeypatch.setattr(runner, "_PROXY_CACHE", {})
    monkeypatch.setattr(runner, "score_linked_context", lambda *args: calls.append(1) or {"score": 1})
    runner._proxy("linked", [], {}, None, {"docs_top_k": 5})
    cached = runner._proxy("linked", [], {}, None, {"docs_top_k": 5})
    assert cached["cache_hit"] and len(calls) == 1
    runner._proxy("linked", [], {}, None, {"docs_top_k": 8})
    assert len(calls) == 2


def _case(database: str, difficulty: str, index: int):
    return SimpleNamespace(
        db_id=database,
        difficulty=difficulty,
        stable_id=f"dev:{database}:{difficulty}:{index}",
    )


def test_difficulty_balanced_sample_selects_every_database_and_difficulty():
    cases = [
        _case(database, difficulty, index)
        for database in ("a", "b")
        for difficulty in ("simple", "moderate", "challenging")
        for index in range(3)
    ]

    selected = difficulty_balanced_sample(cases, per_database_difficulty=1, seed=42)

    assert len(selected) == 6
    assert {(case.db_id, case.difficulty) for case in selected} == {
        (database, difficulty)
        for database in ("a", "b")
        for difficulty in ("simple", "moderate", "challenging")
    }


def test_best_prefers_execution_then_safety_then_usage():
    def row(accuracy, errors, invalid, tokens):
        return {
            "metrics": {
                "execution_accuracy": accuracy,
                "run_error_rate": errors,
                "invalid_sql_rate": invalid,
                "input_tokens_all_calls": tokens,
                "output_tokens_all_calls": 10,
            }
        }

    rows = [row(0.4, 0.0, 0.1, 100), row(0.5, 0.1, 0.0, 10), row(0.5, 0.0, 0.0, 200)]

    assert _best(rows) is rows[2]


def test_best_keeps_incumbent_when_new_candidate_regresses():
    incumbent = {
        "metrics": {
            "execution_accuracy": 0.6,
            "run_error_rate": 0.0,
            "invalid_sql_rate": 0.0,
            "input_tokens_all_calls": 200,
            "output_tokens_all_calls": 20,
        }
    }
    candidate = {
        "metrics": {
            "execution_accuracy": 0.5,
            "run_error_rate": 0.0,
            "invalid_sql_rate": 0.0,
            "input_tokens_all_calls": 100,
            "output_tokens_all_calls": 10,
        }
    }

    assert _best([incumbent, candidate]) is incumbent

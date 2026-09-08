import pytest

from src.branch_sql_MVP.online.token_budget import TokenBudget, TokenBudgetExceeded


def test_budget_reserves_settles_and_survives_restart(tmp_path):
    path = tmp_path / "tokens.jsonl"
    budget = TokenBudget(path, 100)
    reservation = budget.reserve(80)
    with pytest.raises(TokenBudgetExceeded):
        budget.reserve(30)
    budget.settle(reservation, {"input_tokens": 20, "output_tokens": 10})
    resumed = TokenBudget(path, 100)
    assert resumed.used == 30
    resumed.reserve(70)
    with pytest.raises(TokenBudgetExceeded):
        resumed.reserve(1)


def test_gold_failure_is_not_scored_as_model_error(monkeypatch):
    from types import SimpleNamespace

    from src.branch_sql_MVP.eval import text2sql
    monkeypatch.setattr(text2sql, "execute_readonly_sql", lambda *a, **k: SimpleNamespace(
        model_dump=lambda **k: {"status": "success", "preview": [[1]], "row_count": 1}))
    monkeypatch.setattr(text2sql, "_gold_execution", lambda *a: {"status": "timeout", "error": "interrupted"})
    row = text2sql.evaluate_prediction(SimpleNamespace(gold_sql="SELECT 1"), {"sql": "SELECT 1"}, "unused")
    assert row["execution_correct"] is None
    assert text2sql.aggregate_results([row])["evaluation_error_cases"] == 1

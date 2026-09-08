from dataclasses import replace

from src.branch_sql_MVP.data.catalog import BenchmarkCase
from src.branch_sql_MVP.eval.dataset_split import question_key, split_cases, sql_key


def test_holdout_excludes_exposed_and_duplicate_questions_and_resumes(tmp_path):
    cases = [BenchmarkCase(
        stable_id=f"vi:dev:a:{i}", split="dev", language="vi", question_id=str(i),
        db_id="a", question=f"Câu {i}", evidence="", difficulty="simple", gold_sql=f"SELECT {i}",
        database=None, sql_dump=None, business_document=tmp_path, source=tmp_path,
    ) for i in range(20)]
    cases.append(replace(cases[0], stable_id="vi:dev:a:duplicate"))
    run = tmp_path / "runs"
    run.mkdir()
    (run / "cases.jsonl").write_text('{"stable_id":"vi:dev:a:1"}\n', encoding="utf-8")
    kwargs = {"runtime_root": tmp_path, "manifest_path": tmp_path / "split.json"}
    dev, test = split_cases(cases, [cases[0]], **kwargs)
    assert len(dev) + len(test) == len(cases)
    assert not {question_key(c) for c in dev} & {question_key(c) for c in test}
    assert not {sql_key(c) for c in dev} & {sql_key(c) for c in test}
    assert {cases[0].stable_id, cases[1].stable_id, cases[-1].stable_id} <= {c.stable_id for c in dev}
    assert (dev, test) == split_cases(cases, [], **kwargs)

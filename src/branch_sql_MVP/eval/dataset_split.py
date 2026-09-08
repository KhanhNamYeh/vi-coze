"""Chia theo nhóm câu hỏi; giữ nguyên dữ liệu nguồn và ID để tra artifact."""

from __future__ import annotations

import json
import random
import re
from collections import defaultdict
from pathlib import Path

from ..data.catalog import BenchmarkCase


def question_key(case: BenchmarkCase) -> str:
    return re.sub(r"\W+", "", case.question.casefold())


def sql_key(case: BenchmarkCase) -> tuple[str, str]:
    return case.db_id, re.sub(r"\s+", "", case.gold_sql).casefold()


def split_cases(
    cases: list[BenchmarkCase],
    legacy: list[BenchmarkCase],
    *,
    runtime_root: Path = Path(".runtime"),
    manifest_path: Path = Path(__file__).resolve().parent.joinpath("dataset_split.json"),
    seed: int = 42,
) -> tuple[list[BenchmarkCase], list[BenchmarkCase]]:
    """Holdout 20% mỗi strata; câu đã chạy hoặc trùng legacy chỉ vào dev."""
    lookup = {case.stable_id: case for case in cases}
    if manifest_path.exists():
        saved = json.loads(manifest_path.read_text(encoding="utf-8"))
        if set(saved["dev_ids"] + saved["test_ids"]) != set(lookup):
            raise ValueError("Dữ liệu đã đổi; cần tạo phiên bản split mới")
        return ([lookup[key] for key in saved["dev_ids"]], [lookup[key] for key in saved["test_ids"]])

    exposed = set()
    for path in runtime_root.glob("**/cases.jsonl"):
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                exposed.add(json.loads(line)["stable_id"])
    blocked = {question_key(case) for case in legacy}
    blocked.update(question_key(case) for case in cases if case.stable_id in exposed)
    groups = defaultdict(list)
    for case in cases:
        groups[question_key(case)].append(case)
    strata = defaultdict(list)
    for key, group in sorted(groups.items()):
        first = group[0]
        strata[(first.db_id, first.difficulty)].append(key)
    rng = random.Random(seed)
    test_keys = set()
    for keys in strata.values():
        eligible = [key for key in keys if key not in blocked]
        rng.shuffle(eligible)
        count = max(1, round(len(keys) * 0.2))
        if len(eligible) < count:
            raise ValueError("Không đủ câu chưa dùng để tạo holdout; cần dữ liệu mới")
        test_keys.update(eligible[:count])
    # Giữ nhóm paraphrase cùng gold SQL về dev nếu chạm biên split.
    while True:
        dev_sql = {sql_key(case) for case in cases if question_key(case) not in test_keys}
        overlap = {question_key(case) for case in cases if question_key(case) in test_keys and sql_key(case) in dev_sql}
        if not overlap:
            break
        test_keys.difference_update(overlap)
    dev = [case for case in cases if question_key(case) not in test_keys]
    test = [case for case in cases if question_key(case) in test_keys]
    saved = {
        "protocol": "internal-question-holdout-v1",
        "seed": seed,
        "source": "BIRD dev tiếng Việt; không phải official BIRD test",
        "scope": "Câu hỏi mới trên database đã biết; không đo unseen-database generalization",
        "exposure_note": "Loại ID có trong raw runs và câu trùng legacy; không chứng minh chưa từng được con người xem",
        "dev_ids": [case.stable_id for case in dev],
        "test_ids": [case.stable_id for case in test],
        "previously_run_ids": sorted(exposed & lookup.keys()),
        "legacy_question_overlap": sum(question_key(case) in {question_key(x) for x in cases} for case in legacy),
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(saved, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return dev, test

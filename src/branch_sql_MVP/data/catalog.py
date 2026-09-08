"""Discover datasets from the repository's data directory."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

CASE_MARKER = re.compile(
    r"^--\s*\[question_id=(?P<question_id>[^\]]+)]"
    r"(?:\s*\[difficulty=(?P<difficulty>[^\]]+)])?\s*$"
)
CASE_FIELD = re.compile(r"^--\s*(?P<name>Query|Evidence):\s*(?P<value>.*)$", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class Dataset:
    name: str
    business_document: Path | None
    sql_dump: Path | None
    database: Path | None
    gold_examples: tuple[Path, ...]

    @property
    def complete(self) -> bool:
        has_database_source = self.sql_dump is not None or self.database is not None
        return self.business_document is not None and has_database_source and bool(self.gold_examples)

    def as_dict(self, root: Path | None = None) -> dict[str, object]:
        def display(path: Path | None) -> str | None:
            if path is None:
                return None
            if root is not None:
                try:
                    return path.relative_to(root).as_posix()
                except ValueError:
                    pass
            return str(path)

        return {
            "name": self.name,
            "complete": self.complete,
            "business_document": display(self.business_document),
            "sql_dump": display(self.sql_dump),
            "database": display(self.database),
            "gold_examples": [display(path) for path in self.gold_examples],
        }


@dataclass(frozen=True, slots=True)
class BenchmarkCase:
    """Một case có gold riêng; `workflow_input` tuyệt đối không trả gold SQL."""

    stable_id: str
    split: Literal["dev", "test"]
    language: str
    question_id: str
    db_id: str
    question: str
    evidence: str
    difficulty: str
    gold_sql: str
    database: Path | None
    sql_dump: Path | None
    business_document: Path
    source: Path

    def workflow_input(self, *, database: Path | None = None) -> dict[str, object]:
        selected_database = database or self.database
        if selected_database is None:
            raise FileNotFoundError(f"case '{self.stable_id}' chưa có SQLite database")
        return {
            "stable_id": self.stable_id,
            "split": self.split,
            "language": self.language,
            "question_id": self.question_id,
            "db_id": self.db_id,
            "question": self.question,
            "evidence": self.evidence,
            "difficulty": self.difficulty,
            "database_path": str(selected_database.resolve()),
            "business_path": str(self.business_document.resolve()),
        }


def _stable_id(split: str, db_id: str, question_id: str, language: str = "vi") -> str:
    return f"{language}:{split}:{db_id}:{question_id}"


def _parse_gold_file(path: Path) -> list[dict[str, str]]:
    cases: list[dict[str, object]] = []
    current: dict[str, object] | None = None
    for line in path.read_text(encoding="utf-8").splitlines():
        marker = CASE_MARKER.match(line.strip())
        if marker:
            if current is not None:
                cases.append(current)
            current = {**marker.groupdict(), "sql": []}
            continue
        if current is None:
            continue
        field = CASE_FIELD.match(line.strip())
        if field:
            name = field.group("name").lower()
            current["question" if name == "query" else name] = field.group("value").strip()
        elif line.strip() and not line.lstrip().startswith("--"):
            statements = current["sql"]
            assert isinstance(statements, list)
            statements.append(line.rstrip())
    if current is not None:
        cases.append(current)
    output = []
    for case in cases:
        sql = "\n".join(case["sql"]).strip()
        if not case.get("question") or not sql:
            raise ValueError(f"{path}: case {case.get('question_id')} thiếu question hoặc SQL")
        output.append(
            {
                "question_id": str(case["question_id"]),
                "difficulty": str(case.get("difficulty") or "unknown"),
                "question": str(case["question"]),
                "evidence": str(case.get("evidence") or ""),
                "SQL": sql,
            }
        )
    return output


def load_benchmark_cases(
    data_root: str | Path,
    split: Literal["dev", "test"],
) -> list[BenchmarkCase]:
    """Đọc dev JSON hoặc test gold nhưng giữ gold ngoài payload của workflow."""
    root = Path(data_root).resolve()
    cases: list[BenchmarkCase] = []
    if split == "dev":
        source = root / "dev.json"
        records = json.loads(source.read_text(encoding="utf-8"))
        for record in records:
            db_id = str(record["db_id"])
            question_id = str(record["question_id"])
            cases.append(
                BenchmarkCase(
                    stable_id=_stable_id(split, db_id, question_id),
                    split=split,
                    language="vi",
                    question_id=question_id,
                    db_id=db_id,
                    question=str(record["question"]).strip(),
                    evidence=str(record.get("evidence") or "").strip(),
                    difficulty=str(record.get("difficulty") or "unknown"),
                    gold_sql=str(record["SQL"]).strip(),
                    database=root / "dev_databases" / db_id / f"{db_id}.sqlite",
                    sql_dump=None,
                    business_document=root / "business" / f"{db_id}.md",
                    source=source,
                )
            )
    else:
        for database_dir in sorted((root / "gold").iterdir()):
            if not database_dir.is_dir():
                continue
            db_id = database_dir.name
            business = root / "business" / f"{db_id}.md"
            dump = root / "sql" / f"{db_id}.sql"
            for source in sorted(database_dir.glob("*.sql")):
                for record in _parse_gold_file(source):
                    question_id = record["question_id"]
                    cases.append(
                        BenchmarkCase(
                            stable_id=_stable_id(split, db_id, question_id),
                            split=split,
                            language="vi",
                            question_id=question_id,
                            db_id=db_id,
                            question=record["question"],
                            evidence=record["evidence"],
                            difficulty=record["difficulty"],
                            gold_sql=record["SQL"],
                            database=None,
                            sql_dump=dump,
                            business_document=business,
                            source=source,
                        )
                    )
    stable_ids = [case.stable_id for case in cases]
    if not cases or len(stable_ids) != len(set(stable_ids)):
        raise ValueError(f"split '{split}' rỗng hoặc trùng stable_id")
    for case in cases:
        if case.database is not None and not case.database.is_file():
            raise FileNotFoundError(case.database)
        if case.sql_dump is not None and not case.sql_dump.is_file():
            raise FileNotFoundError(case.sql_dump)
        if not case.business_document.is_file():
            raise FileNotFoundError(case.business_document)
    return sorted(cases, key=lambda case: (case.db_id, case.question_id))


class DatasetCatalog:
    def __init__(self, data_root: str | Path):
        self.root = Path(data_root).resolve()

    def discover(self) -> dict[str, Dataset]:
        business = {path.stem: path for path in (self.root / "business").glob("*.md")}
        dumps = {path.stem: path for path in (self.root / "sql").glob("*.sql")}
        databases: dict[str, Path] = {}
        for directory_name in ("databases", "dev_databases"):
            database_root = self.root / directory_name
            if not database_root.is_dir():
                continue
            for path in sorted(database_root.glob("*/*.sqlite")):
                databases.setdefault(path.parent.name, path)
        gold_root = self.root / "gold"
        gold = (
            {
                directory.name: tuple(sorted(directory.glob("*.sql")))
                for directory in gold_root.iterdir()
                if directory.is_dir()
            }
            if gold_root.is_dir()
            else {}
        )
        names = sorted(set(business) | set(dumps) | set(databases) | set(gold))
        return {
            name: Dataset(name, business.get(name), dumps.get(name), databases.get(name), gold.get(name, ()))
            for name in names
        }

    def get(self, name: str) -> Dataset:
        datasets = self.discover()
        try:
            return datasets[name]
        except KeyError as error:
            available = ", ".join(datasets) or "không có"
            raise KeyError(f"dataset '{name}' không tồn tại; có: {available}") from error

    def list(self) -> list[dict[str, object]]:
        return [dataset.as_dict(self.root) for dataset in self.discover().values()]

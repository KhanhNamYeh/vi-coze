"""Convert curated Text-to-SQL examples into indexable Markdown."""

from __future__ import annotations

import re
from pathlib import Path

CASE_MARKER = re.compile(
    r"^--\s*\[question_id=(?P<question_id>[^\]]+)]"
    r"(?:\s*\[difficulty=(?P<difficulty>[^\]]+)])?\s*$"
)
COMMENT_FIELD = re.compile(r"^--\s*(?P<name>Query|Evidence):\s*(?P<value>.*)$", re.IGNORECASE)


def _case_markdown(case: dict[str, object]) -> str:
    question_id = str(case["question_id"])
    difficulty = str(case.get("difficulty") or "unknown")
    query = str(case.get("query") or "").strip()
    evidence = str(case.get("evidence") or "").strip()
    sql = "\n".join(case.get("sql", [])).strip()
    if not query or not sql:
        raise ValueError(f"question_id={question_id}: thiếu Query hoặc câu SQL")
    return (
        f"## Gold sample {question_id} · {difficulty}\n\n"
        f"-- Query: {query}\n"
        f"-- Evidence: {evidence}\n"
        f"```sql\n{sql}\n```"
    )


def to_markdown(path: str | Path) -> str:
    """Parse BIRD-style gold SQL; database dumps are rejected deliberately."""
    source = Path(path)
    cases: list[dict[str, object]] = []
    current: dict[str, object] | None = None

    for line in source.read_text(encoding="utf-8").splitlines():
        marker = CASE_MARKER.match(line.strip())
        if marker:
            if current is not None:
                cases.append(current)
            current = {**marker.groupdict(), "sql": []}
            continue
        if current is None:
            continue
        field = COMMENT_FIELD.match(line.strip())
        if field:
            current[field.group("name").lower()] = field.group("value").strip()
        elif line.strip() and not line.lstrip().startswith("--"):
            cast_sql = current["sql"]
            assert isinstance(cast_sql, list)
            cast_sql.append(line.rstrip())
    if current is not None:
        cases.append(current)
    if not cases:
        raise ValueError(
            f"{source.name} không phải tập gold query (không có question_id); hãy nạp SQL dump bằng lệnh build-db"
        )

    title = source.parent.name if source.parent.name != "gold" else source.stem
    sections = [_case_markdown(case) for case in cases]
    return f"# {title} · {source.stem}\n\n" + "\n\n".join(sections) + "\n"

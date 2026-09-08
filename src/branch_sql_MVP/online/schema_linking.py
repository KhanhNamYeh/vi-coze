"""Schema và value linking không gọi LLM, trả evidence có provenance."""

from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher
from typing import Any


def _normalize(text: str) -> str:
    value = unicodedata.normalize("NFD", str(text).casefold())
    value = "".join(character for character in value if unicodedata.category(character) != "Mn")
    return re.sub(r"[^a-z0-9]+", " ", value.replace("đ", "d")).strip()


def _tokens(text: str) -> set[str]:
    return {token for token in _normalize(text).split() if len(token) > 1}


def _score(question: str, name: str, description: str) -> float:
    query = _normalize(question)
    label = _normalize(name.replace("_", " "))
    body = _normalize(description)
    query_tokens = _tokens(query)
    item_tokens = _tokens(f"{label} {body}")
    overlap = len(query_tokens & item_tokens) / max(len(query_tokens), 1)
    exact = 1.0 if label and label in query else 0.0
    fuzzy = max((SequenceMatcher(None, token, label).ratio() for token in query_tokens), default=0.0)
    return 3.0 * exact + 1.5 * overlap + 0.5 * fuzzy


def link_schema_elements(
    question: str,
    catalog: dict[str, Any],
    *,
    table_k: int = 5,
    column_k: int = 12,
    min_score: float = 0.12,
) -> list[dict[str, Any]]:
    tables = []
    columns = []
    for table in catalog["tables"]:
        table_description = " ".join(
            str(column.get("description") or "") for column in table["columns"]
        )
        tables.append((_score(question, table["name"], table_description), table))
        for column in table["columns"]:
            description = " ".join(
                str(column.get(field) or "")
                for field in ("business_name", "description", "format", "value_description")
            )
            columns.append((_score(question, f"{table['name']} {column['name']}", description), table, column))
    selected_tables = [item for item in sorted(tables, key=lambda item: (-item[0], item[1]["name"])) if item[0] >= min_score][
        :table_k
    ]
    selected_columns = [
        item
        for item in sorted(columns, key=lambda item: (-item[0], item[1]["name"], item[2]["name"]))
        if item[0] >= min_score
    ][:column_k]
    output = []
    selected_table_names = {table["name"] for _, table in selected_tables}
    selected_table_names.update(table["name"] for _, table, _ in selected_columns)
    for score, table in selected_tables:
        output.append(
            {
                "id": f"schema:{catalog['database_id']}:table:{table['name']}",
                "kind": "schema",
                "text": str(table["ddl"]).strip(),
                "source": catalog["database_path"],
                "score": score,
                "metadata": {"table": table["name"], "link_method": "lexical_fuzzy"},
            }
        )
    for score, table, column in selected_columns:
        details = " | ".join(
            str(column.get(field) or "")
            for field in ("business_name", "description", "format", "value_description")
            if column.get(field)
        )
        output.append(
            {
                "id": f"schema:{catalog['database_id']}:column:{table['name']}:{column['name']}",
                "kind": "schema",
                "text": f"{table['name']}.{column['name']} {column['type']}: {details}".rstrip(": "),
                "source": column.get("description_source") or catalog["database_path"],
                "score": score,
                "metadata": {
                    "table": table["name"],
                    "column": column["name"],
                    "link_method": "lexical_fuzzy",
                },
            }
        )
    # Luôn bổ sung FK giữa các bảng đã link để context có đường join hoàn chỉnh.
    for table in catalog["tables"]:
        for foreign_key in table["foreign_keys"]:
            if table["name"] not in selected_table_names and foreign_key["to_table"] not in selected_table_names:
                continue
            target = foreign_key.get("to_column") or "<unknown>"
            output.append(
                {
                    "id": (
                        f"schema:{catalog['database_id']}:fk:{table['name']}:"
                        f"{foreign_key['from_column']}:{foreign_key['to_table']}:{target}"
                    ),
                    "kind": "schema",
                    "text": (
                        f"FOREIGN KEY {table['name']}.{foreign_key['from_column']} -> "
                        f"{foreign_key['to_table']}.{target}"
                    ),
                    "source": catalog["database_path"],
                    "score": 1.0,
                    "metadata": {"table": table["name"], "target_table": foreign_key["to_table"]},
                }
            )
    return _dedupe(output)


def link_literal_values(
    question: str,
    catalog: dict[str, Any],
    *,
    top_k: int = 10,
    fuzzy_threshold: float = 0.84,
) -> list[dict[str, Any]]:
    normalized_question = _normalize(question)
    query_tokens = _tokens(question)
    scored = []
    for table in catalog["tables"]:
        for column in table["columns"]:
            for value in column.get("sample_values", []):
                normalized_value = _normalize(str(value))
                if not normalized_value:
                    continue
                exact = normalized_value in normalized_question
                fuzzy = max(
                    (SequenceMatcher(None, token, normalized_value).ratio() for token in query_tokens),
                    default=0.0,
                )
                semantic = len(_tokens(normalized_value) & query_tokens) / max(len(_tokens(normalized_value)), 1)
                score = 2.0 if exact else max(fuzzy, semantic)
                if exact or fuzzy >= fuzzy_threshold or semantic >= 0.5:
                    scored.append((score, table, column, value, "exact" if exact else "fuzzy_semantic"))
    scored.sort(key=lambda item: (-item[0], item[1]["name"], item[2]["name"], str(item[3])))
    return [
        {
            "id": f"value:{catalog['database_id']}:{table['name']}:{column['name']}:{index}",
            "kind": "value",
            "text": f"{table['name']}.{column['name']} có giá trị liên quan: {value}",
            "source": catalog["database_path"],
            "score": score,
            "metadata": {
                "table": table["name"],
                "column": column["name"],
                "value": value,
                "link_method": method,
            },
        }
        for index, (score, table, column, value, method) in enumerate(scored[:top_k], 1)
    ]


def _dedupe(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return list({item["id"]: item for item in items}.values())

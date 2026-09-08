"""Index ví dụ Text-to-SQL chỉ nhận corpus được khai báo là train."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any


def _tokens(text: str) -> set[str]:
    return {token.casefold() for token in re.findall(r"[\w]+", text, flags=re.UNICODE) if len(token) > 1}


def build_example_index(records: list[dict[str, Any]], *, corpus_split: str) -> dict[str, Any]:
    if corpus_split != "train":
        raise ValueError("example index chỉ chấp nhận corpus_split='train'")
    examples = []
    for record in records:
        if not record.get("question") or not record.get("SQL"):
            continue
        examples.append(
            {
                "id": f"train:{record.get('db_id', 'unknown')}:{record.get('question_id')}",
                "db_id": str(record.get("db_id") or ""),
                "question": str(record["question"]).strip(),
                "evidence": str(record.get("evidence") or "").strip(),
                "sql": str(record["SQL"]).strip(),
                "tokens": sorted(_tokens(str(record["question"]))),
            }
        )
    canonical = json.dumps(examples, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return {
        "corpus_split": corpus_split,
        "examples": examples,
        "fingerprint": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
    }


def write_example_index(index: dict[str, Any], destination: str | Path) -> Path:
    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def retrieve_similar_examples(
    question: str,
    index: dict[str, Any] | None,
    *,
    database_id: str,
    top_k: int = 3,
) -> list[dict[str, Any]]:
    if not index or index.get("corpus_split") != "train":
        return []
    query_tokens = _tokens(question)
    scored = []
    for example in index.get("examples", []):
        if example.get("db_id") != database_id:
            continue
        tokens = set(example.get("tokens", []))
        score = len(query_tokens & tokens) / max(len(query_tokens | tokens), 1)
        if score:
            scored.append((score, example))
    scored.sort(key=lambda item: (-item[0], item[1]["id"]))
    return [
        {
            "id": example["id"],
            "kind": "example",
            "text": f"Câu hỏi train: {example['question']}\nSQL: {example['sql']}",
            "source": "train-example-index",
            "score": score,
            "metadata": {"db_id": database_id, "corpus_split": "train"},
        }
        for score, example in scored[:top_k]
    ]


"""Metric retrieval độc lập với offline pipeline."""

from __future__ import annotations


def evaluate(cases: list[dict], search) -> dict[str, float]:
    """Mỗi case cần `query` và `relevant_ids`; search(query) trả list hit."""
    if not cases:
        raise ValueError("eval cần ít nhất một case")
    recalls: list[float] = []
    reciprocal_ranks: list[float] = []
    for case in cases:
        relevant = set(case["relevant_ids"])
        hits = search(case["query"])
        ids = [hit.get("metadata", {}).get("id") or hit.get("metadata", {}).get("parent_id") for hit in hits]
        recalls.append(len(relevant.intersection(ids)) / len(relevant) if relevant else 0.0)
        rank = next((index for index, item in enumerate(ids, 1) if item in relevant), None)
        reciprocal_ranks.append(1 / rank if rank else 0.0)
    return {
        "recall": sum(recalls) / len(recalls),
        "mrr": sum(reciprocal_ranks) / len(reciprocal_ranks),
        "cases": float(len(cases)),
    }

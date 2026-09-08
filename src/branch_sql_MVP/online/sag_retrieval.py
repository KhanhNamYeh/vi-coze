"""Seed retrieval và bounded relational expansion trên event–entity artifact."""

from __future__ import annotations

import re
import unicodedata
from typing import Any


def _normalize(text: str) -> str:
    value = unicodedata.normalize("NFD", str(text).casefold())
    value = "".join(character for character in value if unicodedata.category(character) != "Mn")
    return re.sub(r"[^a-z0-9]+", " ", value.replace("đ", "d")).strip()


def _tokens(text: str) -> set[str]:
    return {token for token in _normalize(text).split() if len(token) > 1}


def identify_query_entities(question: str, evidence: list[dict[str, Any]], index: dict[str, Any]) -> list[str]:
    context = f"{question} " + " ".join(item.get("text", "") for item in evidence)
    normalized = _normalize(context)
    tokens = _tokens(context)
    matched = []
    for entity in index["entities"]:
        name = _normalize(entity["name"].replace("_", " "))
        if name and (name in normalized or _tokens(name) & tokens):
            matched.append(entity["id"])
    return sorted(set(matched))


def retrieve_seed_events(
    question: str,
    evidence: list[dict[str, Any]],
    index: dict[str, Any],
    *,
    top_k: int = 8,
) -> list[str]:
    query_tokens = _tokens(f"{question} " + " ".join(item.get("text", "") for item in evidence))
    entity_ids = set(identify_query_entities(question, evidence, index))
    event_entities: dict[str, set[str]] = {}
    for edge in index["edges"]:
        event_entities.setdefault(edge["event_id"], set()).add(edge["entity_id"])
    scored = []
    for event in index["events"]:
        event_tokens = _tokens(event["text"])
        lexical = len(query_tokens & event_tokens) / max(len(query_tokens), 1)
        linked = len(entity_ids & event_entities.get(event["id"], set()))
        score = lexical + 0.5 * linked
        if score:
            scored.append((score, event["id"]))
    scored.sort(key=lambda item: (-item[0], item[1]))
    return [event_id for _, event_id in scored[:top_k]]


def expand_event_neighborhood(
    seed_event_ids: list[str],
    index: dict[str, Any],
    *,
    hops: int = 1,
    node_budget: int = 24,
    token_budget: int = 1800,
) -> list[dict[str, Any]]:
    if hops < 0 or hops > 3:
        raise ValueError("hops phải trong khoảng 0..3")
    if node_budget < 1 or token_budget < 1:
        raise ValueError("node_budget và token_budget phải lớn hơn 0")
    events = {event["id"]: event for event in index["events"]}
    event_entities: dict[str, set[str]] = {}
    entity_events: dict[str, set[str]] = {}
    for edge in index["edges"]:
        event_entities.setdefault(edge["event_id"], set()).add(edge["entity_id"])
        entity_events.setdefault(edge["entity_id"], set()).add(edge["event_id"])
    selected: list[str] = []
    frontier = list(dict.fromkeys(seed_event_ids))
    seen = set(frontier)
    for depth in range(hops + 1):
        next_frontier = []
        for event_id in frontier:
            if event_id in events and event_id not in selected:
                selected.append(event_id)
            if len(selected) >= node_budget:
                break
            if depth < hops:
                for entity_id in sorted(event_entities.get(event_id, set())):
                    for neighbor in sorted(entity_events.get(entity_id, set())):
                        if neighbor not in seen:
                            seen.add(neighbor)
                            next_frontier.append(neighbor)
        if len(selected) >= node_budget:
            break
        frontier = next_frontier

    output = []
    used_tokens = 0
    for event_id in selected:
        event = events[event_id]
        estimated = max(1, len(event["text"]) // 4)
        if output and used_tokens + estimated > token_budget:
            break
        used_tokens += estimated
        output.append(
            {
                "id": event_id,
                "kind": "event",
                "text": event["text"],
                "source": event["source"],
                "score": 1.0,
                "metadata": {
                    "event_kind": event["kind"],
                    "entity_ids": sorted(event_entities.get(event_id, set())),
                    "hops": hops,
                },
            }
        )
    return output

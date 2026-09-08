"""Thiết lập cách LLM trả lời; mỗi lời gọi độc lập, không memory hoặc log."""

from __future__ import annotations

import json

from langchain_core.messages import HumanMessage, SystemMessage

from ..settings import Settings, load_settings
from .api import build_model
from .retrieval import retrieve_both


def _options(settings: Settings) -> dict:
    cfg = settings.llm
    values = {
        "temperature": cfg.temperature,
        "max_tokens": cfg.max_tokens,
        "top_p": cfg.top_p,
        "stop": cfg.stop or None,
        **cfg.extra,
    }
    return {key: value for key, value in values.items() if value is not None}


def answer(
    query: str,
    context: dict[str, list[dict]],
    *,
    settings: Settings | None = None,
    provider: str | None = None,
    model: str | None = None,
    api_key: str | None = None,
) -> str:
    app = settings or load_settings()
    llm = build_model(
        settings=app,
        provider=provider,
        model=model,
        api_key=api_key,
        model_options=_options(app),
    )
    if app.llm.structured_output:
        llm = llm.with_structured_output(app.llm.structured_output)
    evidence = "\n\n".join(
        f"[{kind.upper()} {number}]\n{hit['text']}"
        for kind in ("docs", "sql", "graph")
        for number, hit in enumerate(context.get(kind, []), 1)
    )
    messages = [
        SystemMessage(content=app.llm.system_prompt),
        HumanMessage(content=f"Ngữ cảnh:\n{evidence}\n\nCâu hỏi:\n{query}"),
    ]
    response = llm.invoke(messages)
    value = getattr(response, "content", response)
    return json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)


def chat(
    query: str,
    *,
    knowledge_id: str | None = None,
    settings: Settings | None = None,
    provider: str | None = None,
    model: str | None = None,
    api_key: str | None = None,
) -> dict:
    app = settings or load_settings()
    selected_knowledge = knowledge_id or app.index.knowledge_id
    context = retrieve_both(query, knowledge_id=selected_knowledge, settings=app)
    return {
        "knowledge_id": selected_knowledge,
        "answer": answer(query, context, settings=app, provider=provider, model=model, api_key=api_key),
        "context": context,
    }

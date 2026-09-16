"""One configurable LLM executor shared by every LLM node instance."""
from __future__ import annotations
import json
import re
from time import perf_counter
from typing import Any
from langchain_core.messages import HumanMessage, SystemMessage
from ...online.api import build_model
from ...settings import load_settings
from jsonschema import ValidationError, validate

_VARIABLE = re.compile(r"\{\{\s*([A-Za-z][A-Za-z0-9_.-]*)\s*\}\}")

def render_prompt(template: str, inputs: dict[str, Any]) -> str:
    def replace(match: re.Match[str]) -> str:
        value: Any = inputs
        for part in match.group(1).split("."):
            if not isinstance(value, dict) or part not in value:
                raise ValueError(f"thiếu biến prompt: {match.group(1)}")
            value = value[part]
        return json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)
    return _VARIABLE.sub(replace, template)

def invoke_llm(inputs: dict[str, Any], config: dict[str, Any], *, settings=None, api_key=None, **_: Any) -> dict[str, Any]:
    app = (settings or load_settings()).model_copy(deep=True)
    if "timeout" in config or "retries" in config:
        from ...settings import APISettings
        app.api = APISettings.model_validate({**app.api.model_dump(), **{k: config[k] for k in ("timeout", "retries") if k in config}})
        if app.api.retries > 5:
            raise ValueError("LLM retries must be <= 5")
    system = render_prompt(config.get("system_prompt", app.llm.system_prompt), inputs)
    human = render_prompt(config["user_prompt"], inputs)
    provider = config.get("provider", app.api.provider)
    model = config.get("model", app.api.model)
    started = perf_counter()
    options = {k: getattr(app.llm, k) for k in ("temperature", "max_tokens", "top_p", "stop") if getattr(app.llm, k) is not None}
    options.update(app.llm.extra)
    options.update({k: config[k] for k in ("temperature", "max_tokens", "top_p", "stop") if k in config})
    llm = build_model(settings=app, provider=provider, model=model, api_key=api_key or config.get("api_key"), model_options=options)
    messages = [SystemMessage(content=system), HumanMessage(content=human)]
    if config.get("structured") and config.get("response_format") == "json":
        response = llm.with_structured_output(config["output_schema"], include_raw=True).invoke(messages)
        if response.get("parsing_error") or response.get("parsed") is None:
            raise ValueError("LLM structured output không hợp lệ")
        parsed = response["parsed"]
        if hasattr(parsed, "model_dump"):
            parsed = parsed.model_dump(mode="json")
        raw_response = response.get("raw")
        from types import SimpleNamespace
        response = SimpleNamespace(content=json.dumps(parsed, ensure_ascii=False), usage_metadata=getattr(raw_response, "usage_metadata", {}) or {})
    else:
        response = llm.invoke(messages)
    raw = getattr(response, "content", response)
    text = raw if isinstance(raw, str) else json.dumps(raw, ensure_ascii=False, default=str)
    value: Any = text
    if config.get("response_format") == "json":
        try:
            value = json.loads(text)
        except json.JSONDecodeError as error:
            raise ValueError(f"LLM trả JSON không hợp lệ: {error}") from error
        schema = config.get("output_schema")
        if schema:
            try:
                validate(value, schema)
            except ValidationError as error:
                raise ValueError(f"LLM JSON không khớp output_schema: {error.message}") from error
    return {"text": text, "json": value if config.get("response_format") == "json" else {}, "usage": getattr(response, "usage_metadata", {}) or {}, "model": model, "latency": perf_counter() - started}

def preview_prompt(inputs: dict[str, Any], config: dict[str, Any], *, settings=None) -> dict[str, str]:
    app = settings or load_settings()
    return {"system": render_prompt(config.get("system_prompt", app.llm.system_prompt), inputs), "user": render_prompt(config["user_prompt"], inputs)}

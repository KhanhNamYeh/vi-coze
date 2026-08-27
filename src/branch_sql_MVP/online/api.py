"""Kết nối API/provider và khai báo model LLM; không chứa prompt sinh câu trả lời."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from ..settings import Settings, load_settings

ENV_FILE = Path(__file__).resolve().parents[3] / ".env"


def load_env(path: Path = ENV_FILE) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def build_model(
    *,
    settings: Settings | None = None,
    provider: str | None = None,
    model: str | None = None,
    api_key: str | None = None,
    model_options: dict[str, Any] | None = None,
):
    app = settings or load_settings()
    load_env()
    provider_name = provider or app.api.provider
    if provider_name not in app.api.providers:
        raise ValueError(f"provider '{provider_name}' chưa khai báo")
    provider_cfg = app.api.providers[provider_name]
    secret = api_key or os.getenv(provider_cfg.api_key_env)
    if not secret:
        raise RuntimeError(f"thiếu API key: nhập trên UI hoặc đặt {provider_cfg.api_key_env}")
    base_url = provider_cfg.base_url or (
        os.getenv(provider_cfg.base_url_env) if provider_cfg.base_url_env else None
    )
    options = {**(model_options or {})}
    model_name = model or app.api.model

    if provider_cfg.binding == "google":
        from langchain_google_genai import ChatGoogleGenerativeAI

        return ChatGoogleGenerativeAI(model=model_name, google_api_key=secret, **options)
    if provider_cfg.binding == "nvidia":
        from langchain_nvidia_ai_endpoints import ChatNVIDIA

        return ChatNVIDIA(model=model_name, api_key=secret, base_url=base_url, **options)

    from langchain_openai import ChatOpenAI

    return ChatOpenAI(
        model=model_name,
        api_key=secret,
        base_url=base_url,
        timeout=app.api.timeout,
        max_retries=app.api.retries,
        default_headers=provider_cfg.headers or None,
        **options,
    )

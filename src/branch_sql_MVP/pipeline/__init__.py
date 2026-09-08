"""LangGraph orchestration cho các kịch bản benchmark Text-to-SQL."""

from __future__ import annotations


def build_workflow(*args, **kwargs):
    from .registry import build_workflow as factory

    return factory(*args, **kwargs)


__all__ = ["build_workflow"]

"""Registry benchmark ID -> workflow builder; ID không xuất hiện trong tên node nghiệp vụ."""

from __future__ import annotations

from typing import Literal

from ..settings import Settings
from .adaptive_workflow import build_adaptive_workflow
from .execution_repair import build_repair_workflow
from .hybrid_context import build_hybrid_workflow
from .prompt_baseline import build_prompt_workflow
from .sag_context import build_relational_workflow

Scenario = Literal["P1", "B4", "B5", "B6", "G1"]

BUILDERS = {
    "P1": build_prompt_workflow,
    "B4": build_hybrid_workflow,
    "B5": build_relational_workflow,
    "B6": build_repair_workflow,
    "G1": build_adaptive_workflow,
}


def build_workflow(
    scenario: Scenario,
    settings: Settings,
    *,
    provider: str | None = None,
    model: str | None = None,
    api_key: str | None = None,
):
    try:
        builder = BUILDERS[scenario]
    except KeyError as error:
        raise ValueError(f"scenario '{scenario}' không hợp lệ; có: {', '.join(BUILDERS)}") from error
    return builder(settings, provider=provider, model=model, api_key=api_key)

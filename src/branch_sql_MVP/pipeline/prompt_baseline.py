"""Backward-compatible P1 builder using the shared workflow compiler."""
from .compatibility import LegacyWorkflow

def build_prompt_workflow(settings, *, provider=None, model=None, api_key=None):
    return LegacyWorkflow("P1", settings, provider=provider, model=model, api_key=api_key)

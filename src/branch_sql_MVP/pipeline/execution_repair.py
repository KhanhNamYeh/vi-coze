"""Backward-compatible B6 builder using the shared workflow compiler."""
from .compatibility import LegacyWorkflow

def build_repair_workflow(settings, *, provider=None, model=None, api_key=None):
    return LegacyWorkflow("B6", settings, provider=provider, model=model, api_key=api_key)

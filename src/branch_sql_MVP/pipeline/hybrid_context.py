"""Backward-compatible B4 builder using the shared workflow compiler."""
from .compatibility import LegacyWorkflow

def build_hybrid_workflow(settings, *, provider=None, model=None, api_key=None):
    return LegacyWorkflow("B4", settings, provider=provider, model=model, api_key=api_key)

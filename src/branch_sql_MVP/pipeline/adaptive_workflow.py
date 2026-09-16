"""Backward-compatible G1 builder using the shared workflow compiler."""
from .compatibility import LegacyWorkflow

def build_adaptive_workflow(settings, *, provider=None, model=None, api_key=None):
    return LegacyWorkflow("G1", settings, provider=provider, model=model, api_key=api_key)

"""Backward-compatible B5 builder using the shared workflow compiler."""
from .compatibility import LegacyWorkflow

def build_relational_workflow(settings, *, provider=None, model=None, api_key=None):
    return LegacyWorkflow("B5", settings, provider=provider, model=model, api_key=api_key)

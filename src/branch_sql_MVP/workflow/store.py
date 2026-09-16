"""Atomic revision storage shared by the editor and runtime."""
from __future__ import annotations
import os
import re
from pathlib import Path
from threading import RLock
from uuid import uuid4
from .contracts import WorkflowDefinition

_LOCK = RLock()

def checked_id(value: str) -> str:
    if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]{0,63}', value):
        raise ValueError('invalid workflow id')
    return value

def atomic_write(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.' + uuid4().hex + '.tmp')
    try:
        temporary.write_text(text, encoding='utf-8')
        # Windows readers/virus scanners may briefly deny replacing an open file.
        # Retry only the atomic rename; never repeat a stage's external side effect.
        from time import sleep
        for attempt in range(6):
            try:
                os.replace(temporary,path)
                break
            except PermissionError:
                if attempt==5:
                    raise
                sleep(.05*(attempt+1))
    finally:
        temporary.unlink(missing_ok=True)

def save_workflow(root: Path, workflow: WorkflowDefinition, *, expected_revision: int | None = None) -> WorkflowDefinition:
    path = root / f'{checked_id(workflow.id)}.json'
    with _LOCK:
        if path.exists():
            current = load_workflow(root, workflow.id)
            if expected_revision is None or current.revision != expected_revision:
                raise ValueError(f'revision conflict: expected {expected_revision}, found {current.revision}')
            # Preserve definitions written by earlier versions of the store too.
            old = root / 'revisions' / workflow.id / f'{current.revision}.json'
            if not old.exists():
                atomic_write(old, current.model_dump_json(indent=2))
            workflow = workflow.model_copy(update={'revision': current.revision + 1}, deep=True)
        elif expected_revision is not None:
            raise FileNotFoundError(path)
        else:
            workflow = workflow.model_copy(update={'revision': 1}, deep=True)
        atomic_write(root / 'revisions' / workflow.id / f'{workflow.revision}.json', workflow.model_dump_json(indent=2))
        atomic_write(path, workflow.model_dump_json(indent=2))
        return workflow

def load_workflow(root: Path, workflow_id: str, revision: int | None = None) -> WorkflowDefinition:
    checked_id(workflow_id)
    if revision is not None and revision < 1:
        raise ValueError('revision must be positive')
    path = root / f'{workflow_id}.json' if revision is None else root / 'revisions' / workflow_id / f'{revision}.json'
    return WorkflowDefinition.model_validate_json(path.read_text(encoding='utf-8'))

def list_workflows(root: Path) -> list[WorkflowDefinition]:
    return [WorkflowDefinition.model_validate_json(path.read_text(encoding='utf-8')) for path in sorted(root.glob('*.json'))]

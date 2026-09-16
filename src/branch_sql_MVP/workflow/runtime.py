"""Durable local jobs. Events survive browser disconnects and process restart."""
from __future__ import annotations

import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from uuid import uuid4

from .compiler import compile_workflow, resolve_workflow_outputs
from .contracts import _is_secret_key

TERMINAL = {'completed', 'failed', 'cancelled', 'interrupted'}


def timestamp():
    return datetime.now(timezone.utc).isoformat()


def sanitize(value, secret=None):
    if isinstance(value, dict):
        return {k: '[redacted]' if _is_secret_key(k) else sanitize(v, secret) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [sanitize(v, secret) for v in value]
    if isinstance(value, str) and secret:
        return value.replace(secret, '[redacted]')
    return value


class RunManager:
    """One manager per app process; SQLite serializes persistent mutations."""

    def __init__(self, root: Path):
        root.mkdir(parents=True, exist_ok=True)
        self.path = root / 'runs.sqlite'
        self.lock = RLock()
        self.pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix='studio-run')
        with self.connection() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS runs (
                    id TEXT PRIMARY KEY, status TEXT NOT NULL, record TEXT NOT NULL,
                    cancel INTEGER NOT NULL DEFAULT 0);
                CREATE TABLE IF NOT EXISTS events (
                    run_id TEXT NOT NULL, sequence INTEGER NOT NULL, event TEXT NOT NULL,
                    PRIMARY KEY(run_id, sequence));
            ''')
            stale = db.execute("SELECT id FROM runs WHERE status IN ('queued','running')").fetchall()
        for row in stale:
            self.finish(row[0], 'interrupted', error='App stopped before this run finished.')

    def connection(self):
        return sqlite3.connect(self.path, timeout=30)

    def get(self, run_id):
        with self.connection() as db:
            row = db.execute('SELECT record FROM runs WHERE id=?', (run_id,)).fetchone()
        if row is None:
            raise FileNotFoundError(run_id)
        return json.loads(row[0])

    def list(self):
        with self.connection() as db:
            return [json.loads(row[0]) for row in db.execute('SELECT record FROM runs ORDER BY rowid DESC LIMIT 100')]

    def event(self, run_id, event_type, **data):
        with self.lock, self.connection() as db:
            sequence = db.execute('SELECT COALESCE(MAX(sequence),0)+1 FROM events WHERE run_id=?', (run_id,)).fetchone()[0]
            event = {'run_id': run_id, 'sequence': sequence, 'timestamp': timestamp(), 'type': event_type, **data}
            db.execute('INSERT INTO events VALUES (?,?,?)', (run_id, sequence, json.dumps(event, ensure_ascii=False, default=str)))
        return event

    def events(self, run_id, after=0):
        self.get(run_id)
        with self.connection() as db:
            return [json.loads(row[0]) for row in db.execute('SELECT event FROM events WHERE run_id=? AND sequence>? ORDER BY sequence', (run_id, after))]

    def cancelled(self, run_id):
        with self.connection() as db:
            return bool(db.execute('SELECT cancel FROM runs WHERE id=?', (run_id,)).fetchone()[0])

    def cancel(self, run_id):
        with self.lock, self.connection() as db:
            record = self.get(run_id)
            if record['status'] not in TERMINAL:
                db.execute('UPDATE runs SET cancel=1 WHERE id=?', (run_id,))
        return self.get(run_id)

    def finish(self, run_id, status, **data):
        with self.lock, self.connection() as db:
            record = self.get(run_id)
            record.update(status=status, **data)
            if status in TERMINAL:
                record['finished_at'] = timestamp()
            db.execute('UPDATE runs SET status=?, record=? WHERE id=?',
                       (status, json.dumps(record, ensure_ascii=False, default=str), run_id))
        if status in {'failed', 'cancelled', 'interrupted'}:
            self._offline_status(record, status, data.get('error'))
        self.event(run_id, 'run_' + status, **data)
        return record

    @staticmethod
    def _offline_name(definition):
        if definition.get('kind') != 'offline':
            return None
        import re
        start = next((n for n in definition.get('nodes', []) if n['type']=='start'), {})
        name = start.get('inputs', {}).get('name', {}).get('value')
        return name if isinstance(name,str) and re.fullmatch(r'[a-z][a-z0-9_]{0,63}',name) else None

    def _offline_status(self, record, status, error):
        name=self._offline_name(record.get('definition', {}))
        if not name:
            return
        from ..data.import_dataset import workspace
        from .store import atomic_write
        path=workspace()/name/'offline-status.json'
        # Registration is the commit point: a late cancel cannot unpublish ready data.
        if (path.parent/'dataset.json').exists():
            return
        payload=json.loads(path.read_text(encoding='utf-8')) if path.exists() else {'id':name,'stages':{}}
        payload.update(status=status, run_id=record['id'], error=error)
        atomic_write(path,json.dumps(payload,ensure_ascii=False,indent=2))

    def submit(self, definition, inputs, settings, *, api_key=None, dataset_revision=None):
        definition = definition.model_copy(deep=True)
        settings = settings.model_copy(deep=True)
        inputs = json.loads(json.dumps(inputs))
        # Validation and compilation precede enqueue; no external calls here.
        compile_workflow(definition, settings=settings)
        run_id = uuid4().hex
        record = sanitize({'id': run_id, 'workflow_id': definition.id,
                           'revision': definition.revision, 'dataset_revision': dataset_revision,
                           'definition': definition.model_dump(mode='json'),
                           'settings': settings.model_dump(mode='json'), 'inputs': inputs,
                           'status': 'queued', 'created_at': timestamp()}, api_key)
        with self.lock, self.connection() as db:
            name=self._offline_name(record['definition'])
            if name:
                active=db.execute("SELECT record FROM runs WHERE status IN ('queued','running')").fetchall()
                if any(self._offline_name(json.loads(row[0]).get('definition',{}))==name for row in active):
                    raise ValueError('An offline run is already active for this dataset')
            db.execute('INSERT INTO runs(id,status,record) VALUES (?,?,?)',
                       (run_id, 'queued', json.dumps(record, ensure_ascii=False)))
        self.event(run_id, 'run_queued')
        self.pool.submit(self._execute, run_id, definition, inputs, settings, api_key)
        return record

    def _execute(self, run_id, definition, inputs, settings, api_key):
        def emit(event_type, **data):
            return self.event(run_id, event_type, **sanitize(data, api_key))
        try:
            if self.cancelled(run_id):
                raise InterruptedError('Cancelled before execution')
            self.finish(run_id, 'running')
            graph = compile_workflow(definition, settings=settings, emit=emit,
                                     cancelled=lambda: self.cancelled(run_id), api_key=api_key)
            result = graph.invoke({'inputs': inputs, 'node_outputs': {}, 'invocations': {}})
            registered = definition.kind == 'offline' and result.get('node_outputs', {}).get('register', {}).get('dataset')
            if self.cancelled(run_id) and not registered:
                raise InterruptedError('Cancelled at completion boundary')
            outputs = resolve_workflow_outputs(definition, result.get('node_outputs', {}))
            self.finish(run_id, 'completed', result=sanitize(result, api_key), outputs=sanitize(outputs, api_key))
        except InterruptedError as error:
            self.finish(run_id, 'cancelled', error=str(error))
        except Exception as error:
            self.finish(run_id, 'failed', error=sanitize(str(error), api_key))

    def close(self):
        self.pool.shutdown(wait=True, cancel_futures=False)

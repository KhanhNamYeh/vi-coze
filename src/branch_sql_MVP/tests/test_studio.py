"""Kiểm thử tích hợp Studio bằng workflow thật với model giả, không gọi API."""
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.branch_sql_MVP.app import studio
from src.branch_sql_MVP.pipeline import prompt_baseline


@pytest.fixture
def client():
    api = FastAPI()
    api.include_router(studio.router)
    return TestClient(api)


def test_catalog_replay_and_graph(client):
    pipelines = client.get('/studio/pipelines').json()
    cases = client.get('/studio/cases').json()
    assert len(pipelines) == 8
    assert len(cases) == 99
    assert all('gold_sql' not in case and 'SQL' not in case for case in cases)
    for pipeline in pipelines:
        graph = client.get(f"/studio/pipelines/{pipeline['id']}/graph").json()
        assert {'id': '__start__'} in graph['nodes']
        replay = client.get(f"/studio/pipelines/{pipeline['id']}/replay/{cases[0]['id']}")
        assert replay.status_code == 200
        assert replay.json()['prediction']['sql']
    edges = client.get('/studio/pipelines/B6-hybrid/graph').json()['edges']
    assert any(e['source'] == 'repair_candidate' and e['target'] == 'observe_latest_candidate' for e in edges)
    assert client.get('/studio/pipelines/unknown/graph').status_code == 404


def test_live_stream_uses_real_graph_and_does_not_leak_gold(client, monkeypatch):
    received = []

    class Prediction:
        def model_dump(self, **kwargs):
            return {'sql': 'SELECT 1', 'explanation': 'Smoke test'}

    def generate(question, context, **kwargs):
        received.append((question, context))
        return Prediction()

    monkeypatch.setattr(prompt_baseline, 'generate_sql_candidate', generate)
    case = client.get('/studio/cases').json()[0]
    response = client.post('/studio/run', json={'pipeline_id': 'P1-full', 'case_id': case['id'],
                                              'question': 'Smoke test custom question'})
    events = [json.loads(line) for line in response.text.splitlines()]
    assert events[-1]['type'] == 'complete', events
    assert events[-1]['data']['final_prediction']['sql'] == 'SELECT 1'
    assert any(e['type'] == 'tasks' for e in events)
    assert received[0][0] == 'Smoke test custom question'
    assert len(events[-1]['data']['candidates']) == 1
    second = client.post('/studio/run', json={'pipeline_id': 'P1-full', 'case_id': case['id']})
    assert len(json.loads(second.text.splitlines()[-1])['data']['candidates']) == 1


def test_stream_reports_errors_without_secret(client, monkeypatch):
    def fail(*args, **kwargs):
        raise RuntimeError('Failed credential smoke-secret')
    monkeypatch.setattr(prompt_baseline, 'generate_sql_candidate', fail)
    case = client.get('/studio/cases').json()[0]
    response = client.post('/studio/run', json={'pipeline_id':'P1-full', 'case_id':case['id'],
                                               'api_key':'smoke-secret'})
    last = json.loads(response.text.splitlines()[-1])
    assert last['type'] == 'error'
    assert 'smoke-secret' not in last['message']

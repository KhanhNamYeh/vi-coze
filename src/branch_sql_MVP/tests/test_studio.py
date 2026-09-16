"""Kiểm thử tích hợp Studio bằng workflow thật với model giả, không gọi API."""
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.branch_sql_MVP.app import studio
from src.branch_sql_MVP.workflow.nodes import llm as shared_llm
from types import SimpleNamespace

def install_model(monkeypatch, generate):
    def build(**kwargs):
        def invoke(messages):
            human=messages[-1].content
            question=human.split("Câu hỏi: ")[-1]
            prediction=generate(question,human,**kwargs).model_dump()
            return {"parsed": {"confidence": .5, "assumptions": [], **prediction}, "raw": None}
        return SimpleNamespace(with_structured_output=lambda *a,**k:SimpleNamespace(invoke=invoke))
    monkeypatch.setattr(shared_llm,"build_model",build)


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
    assert any(e['target'] == 'repair_loop' for e in edges)
    assert client.get('/studio/pipelines/unknown/graph').status_code == 404


def test_live_stream_uses_real_graph_and_does_not_leak_gold(client, monkeypatch):
    received = []

    class Prediction:
        def model_dump(self, **kwargs):
            return {'sql': 'SELECT 1', 'explanation': 'Smoke test'}

    def generate(question, context, **kwargs):
        received.append((question, context))
        return Prediction()

    install_model(monkeypatch, generate)
    case = client.get('/studio/cases').json()[0]
    response = client.post('/studio/run', json={'pipeline_id': 'P1-full', 'case_id': case['id'],
                                              'question': 'Smoke test custom question'})
    events = [json.loads(line) for line in response.text.splitlines()]
    assert events[-1]['type'] == 'complete', events
    assert events[-1]['data']['final_prediction']['sql'] == 'SELECT 1;'
    assert any(e['type'] == 'tasks' for e in events)
    assert received[0][0] == 'Smoke test custom question'
    assert len(events[-1]['data']['candidates']) == 1
    second = client.post('/studio/run', json={'pipeline_id': 'P1-full', 'case_id': case['id']})
    assert len(json.loads(second.text.splitlines()[-1])['data']['candidates']) == 1


def test_stream_reports_errors_without_secret(client, monkeypatch):
    def fail(*args, **kwargs):
        raise RuntimeError('Failed credential smoke-secret')
    install_model(monkeypatch, fail)
    case = client.get('/studio/cases').json()[0]
    response = client.post('/studio/run', json={'pipeline_id':'P1-full', 'case_id':case['id'],
                                               'api_key':'smoke-secret'})
    last = json.loads(response.text.splitlines()[-1])
    assert last['type'] == 'error'
    assert 'smoke-secret' not in last['message']


@pytest.mark.parametrize('override,expected', [
    ({}, ('google', 'gemini-3.5-flash-lite')),
    ({'provider': 'openai', 'model': 'custom-model'}, ('openai', 'custom-model')),
])
def test_live_model_selection_reaches_generation(client, monkeypatch, override, expected):
    received = []

    class Prediction:
        def model_dump(self, **kwargs):
            return {'sql': 'SELECT 1'}

    def generate(*args, **kwargs):
        received.append(kwargs)
        return Prediction()

    install_model(monkeypatch, generate)
    case = client.get('/studio/cases').json()[0]
    response = client.post('/studio/run', json={'pipeline_id':'P1-full', 'case_id':case['id'], **override})
    assert json.loads(response.text.splitlines()[-1])['type'] == 'complete'
    assert (received[0]['provider'], received[0]['model']) == expected
    assert 'reasoning_effort' not in received[0]['settings'].llm.extra


def test_saving_a_pipeline_is_guarded_by_its_revision(client, tmp_path, monkeypatch):
    """The UI saves lazily under the template id; a stale write must be refused."""
    monkeypatch.setattr(studio,'WORKFLOW_ROOT',tmp_path)
    definition={'id':'guarded','kind':'online','nodes':[{'id':'a','type':'passthrough','label':'A','config':{'value':1}}]}
    created=client.post('/studio/workflows',json=definition)
    assert created.status_code==200,created.text
    assert created.json()['revision']==1
    edited={**created.json()}
    edited['nodes'][0]['config']['value']=2
    updated=client.put('/studio/workflows/guarded',json=edited)
    assert updated.status_code==200,updated.text
    assert updated.json()['revision']==2
    # Re-sending the now-stale revision must not silently clobber revision 2.
    assert client.put('/studio/workflows/guarded',json=edited).status_code==409
    assert client.get('/studio/workflows/guarded').json()['nodes'][0]['config']['value']==2


def test_merge_node_debug_replays_outputs_of_the_referenced_run(client, tmp_path, monkeypatch):
    monkeypatch.setattr(studio,'WORKFLOW_ROOT',tmp_path)
    definition={'id':'merge_debug','kind':'online','nodes':[
        {'id':'left','type':'passthrough','label':'Left','config':{'value':'L'}},
        {'id':'out','type':'merge','label':'Out','config':{'sources':['left','right']}}],
        'edges':[{'source':'left','target':'out'}]}
    assert client.post('/studio/workflows',json=definition).status_code==200
    # Without any state the node reports which branches it needs...
    blind=client.post('/studio/workflows/merge_debug/nodes/out/test',json={'revision':1,'inputs':{}})
    assert blind.status_code==422 and 'left, right' in blind.text
    # ...and a hand-written branch output is enough to debug it.
    supplied=client.post('/studio/workflows/merge_debug/nodes/out/test',
                         json={'revision':1,'inputs':{'right':{'value':'R'}}})
    assert supplied.status_code==200,supplied.text
    assert supplied.json()['node_outputs']['out']=={'value':'R'}


def test_api_key_typed_in_the_ui_reaches_the_model_but_is_never_stored(client, tmp_path, monkeypatch):
    """The Studio key field sends api_key with each run / node test only."""
    from time import monotonic, sleep
    from src.branch_sql_MVP.app import workflow_api
    from src.branch_sql_MVP.workflow.runtime import RunManager
    secret = 'sk-ui-typed-SECRET-4242'
    monkeypatch.setattr(studio, 'WORKFLOW_ROOT', tmp_path / 'workflows')
    runs = RunManager(tmp_path / 'runs')
    monkeypatch.setattr(workflow_api, 'manager', lambda: runs)
    seen = []
    def build(**kwargs):
        seen.append(kwargs.get('api_key'))
        raise RuntimeError('provider rejected key ' + str(kwargs.get('api_key')))
    monkeypatch.setattr(shared_llm, 'build_model', build)
    definition = {'id': 'keyed', 'kind': 'online', 'nodes': [
        {'id': 'ask', 'type': 'llm', 'label': 'Ask', 'config': {'user_prompt': 'hi {{question}}'},
         'inputs': {'question': {'value': 'x'}}}]}
    assert client.post('/studio/workflows', json=definition).status_code == 200

    submitted = client.post('/studio/runs', json={'workflow_id': 'keyed', 'revision': 1, 'inputs': {}, 'api_key': secret})
    assert submitted.status_code == 200, submitted.text
    deadline = monotonic() + 10
    while (record := runs.get(submitted.json()['id']))['status'] not in {'completed', 'failed'}:
        assert monotonic() < deadline, 'run did not finish'
        sleep(.02)
    assert seen == [secret]
    assert record['status'] == 'failed' and '[redacted]' in record['error'] and secret not in json.dumps(record)
    assert secret not in json.dumps(runs.events(record['id'], 0))
    assert all(secret.encode() not in path.read_bytes() for path in (tmp_path / 'runs').rglob('*') if path.is_file())

    tested = client.post('/studio/workflows/keyed/nodes/ask/test', json={'revision': 1, 'inputs': {'question': 'x'}, 'api_key': secret})
    assert tested.status_code == 422 and secret not in tested.text and '[redacted]' in tested.text
    assert seen[-1] == secret
    assert all(secret.encode() not in path.read_bytes() for path in (tmp_path / 'workflows').rglob('*') if path.is_file())


def test_nested_node_can_be_tested_without_running_parent(client, tmp_path, monkeypatch):
    monkeypatch.setattr(studio,'WORKFLOW_ROOT',tmp_path)
    body={'id':'child','kind':'online','nodes':[{'id':'leaf','type':'passthrough','label':'Leaf','config':{'value':42}}]}
    definition={'id':'nested_api','kind':'online','nodes':[{'id':'loop','type':'bounded_loop','label':'Loop','config':{'max_iterations':2,'body':body}}]}
    saved=client.post('/studio/workflows',json=definition)
    assert saved.status_code==200,saved.text
    tested=client.post('/studio/workflows/nested_api/nodes/leaf/test',json={'revision':1,'scope':['loop'],'inputs':{}})
    assert tested.status_code==200,tested.text
    assert tested.json()['node_outputs']=={'leaf':{'value':42}}
    assert len(tested.json()['invocations'])==1
    changed=saved.json();changed['nodes'][0]['type']='invalid'
    assert client.put('/studio/workflows/nested_api',json=changed).status_code!=200
    assert client.get('/studio/workflows/nested_api').json()['revision']==1

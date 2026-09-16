from threading import Event
from time import monotonic, sleep
import pytest
from src.branch_sql_MVP.workflow.contracts import WorkflowDefinition
from src.branch_sql_MVP.workflow.store import save_workflow, load_workflow
from src.branch_sql_MVP.workflow.runtime import RunManager
from src.branch_sql_MVP.workflow.compiler import compile_workflow, merge_invocations
from src.branch_sql_MVP.settings import load_settings


def definition():
    return WorkflowDefinition.model_validate({'id': 'persist', 'kind': 'online', 'nodes': [
        {'id': 'a', 'type': 'passthrough', 'label': 'A', 'config': {'value': 7}}
    ], 'outputs': {'answer': {'node_id': 'a', 'output': 'value'}}})


def wait(manager, run_id):
    deadline = monotonic() + 10
    while monotonic() < deadline:
        record = manager.get(run_id)
        if record['status'] in {'completed','failed','cancelled','interrupted'}:
            return record
        sleep(.01)
    raise AssertionError('run did not finish')


def test_revision_history_conflict_and_path_validation(tmp_path):
    first = save_workflow(tmp_path, definition())
    changed = first.model_copy(deep=True)
    changed.nodes[0].config['value'] = 9
    second = save_workflow(tmp_path, changed, expected_revision=1)
    assert second.revision == 2
    assert load_workflow(tmp_path, first.id, 1).nodes[0].config['value'] == 7
    with pytest.raises(ValueError, match='conflict'):
        save_workflow(tmp_path, changed, expected_revision=1)
    with pytest.raises(ValueError):
        load_workflow(tmp_path, '../escape')


def test_run_persists_snapshot_events_and_invocations(tmp_path):
    manager = RunManager(tmp_path)
    item = definition()
    settings = load_settings()
    run = manager.submit(item, {}, settings, api_key='temporary-secret')
    item.nodes[0].config['value'] = 99
    settings.api.model = 'changed-later'
    result = wait(manager, run['id'])
    manager.close()
    assert result['status'] == 'completed'
    assert result['outputs'] == {'answer': 7}
    assert result['settings']['api']['model'] != 'changed-later'
    assert len(result['result']['invocations']) == 1
    reopened = RunManager(tmp_path)
    events = reopened.events(run['id'])
    assert [e['sequence'] for e in events] == list(range(1, len(events)+1))
    assert reopened.events(run['id'], events[-1]['sequence']) == []
    assert any(e['type'] == 'node_completed' for e in events)
    reopened.close()
    assert b'temporary-secret' not in (tmp_path / 'runs.sqlite').read_bytes()


def test_invocation_collision_and_settings_snapshot():
    with pytest.raises(ValueError, match='collision'):
        merge_invocations({'a': {}}, {'a': {}})
    graph = compile_workflow(definition())
    result = graph.invoke({'inputs': {}, 'node_outputs': {}})
    assert len(result['invocations']) == 1

def test_bounded_loop_and_fanout_preserve_every_invocation():
    body = {'id': 'body', 'kind': 'online', 'nodes': [
        {'id': 'start', 'type': 'start', 'label': 'Start'}
    ], 'outputs': {'continue': {'value': True}, 'item': {'node_id': 'start', 'output': 'item'}}}
    loop = WorkflowDefinition.model_validate({'id': 'loops', 'kind': 'online', 'nodes': [
        {'id': 'loop', 'type': 'bounded_loop', 'label': 'Loop',
         'inputs': {'item': {'value': 'test'}}, 'config': {'body': body, 'max_iterations': 3}}
    ]})
    result = compile_workflow(loop).invoke({'inputs': {}, 'node_outputs': {}})
    output = result['node_outputs']['loop']
    assert len(output['iterations']) == 3 and output['bound_reached']
    ids = [key for row in output['iterations'] for key in row['invocations']]
    assert len(set(ids)) == 3
    each = loop.model_copy(deep=True)
    each.nodes[0].type = 'foreach'
    each.nodes[0].config = {'body': body, 'max_items': 3}
    from src.branch_sql_MVP.workflow.contracts import Reference
    each.nodes[0].inputs = {'items': Reference(value=['a', 'b', 'c'])}
    outputs = compile_workflow(each).invoke({'inputs': {}, 'node_outputs': {}})['node_outputs']['loop']
    assert [row['item'] for row in outputs['items']] == ['a','b','c']
    each.nodes[0].config['max_items'] = 0
    with pytest.raises(ValueError, match='bound'):
        compile_workflow(each)

def test_cancel_at_boundary_and_restart_marks_interrupted(tmp_path, monkeypatch):
    import json
    import src.branch_sql_MVP.workflow.registry as registry
    started=Event(); release=Event()
    original=registry._passthrough
    def block(inputs, config, **kwargs):
        started.set(); assert release.wait(5)
        return original(inputs,config)
    monkeypatch.setattr(registry,'_TYPES',[registry.NodeType(t.type,t.label,t.description,t.config_schema,t.input_schema,t.output_schema,block if t.type=='passthrough' else t.executor) for t in registry._TYPES])
    manager=RunManager(tmp_path)
    row=manager.submit(definition(),{},load_settings())
    assert started.wait(5)
    manager.cancel(row['id']);release.set()
    assert wait(manager,row['id'])['status']=='cancelled'
    manager.close()
    with manager.connection() as db:
        record={'id':'interrupted','status':'running'}
        db.execute('INSERT INTO runs(id,status,record) VALUES (?,?,?)',('interrupted','running',json.dumps(record)))
    restarted=RunManager(tmp_path)
    assert restarted.get('interrupted')['status']=='interrupted'
    restarted.close()


def test_nested_composites_emit_scopes_without_collisions():
    leaf = {'id':'leaf','kind':'online','nodes':[{'id':'start','type':'start','label':'Start'}],
            'outputs':{'item':{'node_id':'start','output':'item'}}}
    middle = {'id':'middle','kind':'online','nodes':[{'id':'inner','type':'foreach','label':'Inner',
              'config':{'body':leaf,'max_items':2},'inputs':{'items':{'value':['x','y']}}}],
              'outputs':{'items':{'node_id':'inner','output':'items'}}}
    outer = WorkflowDefinition.model_validate({'id':'nested','kind':'online','nodes':[
        {'id':'outer','type':'foreach','label':'Outer','config':{'body':middle,'max_items':2},
         'inputs':{'items':{'value':[1,2]}}}]})
    events=[]
    result=compile_workflow(outer,emit=lambda event,**data:events.append({'type':event,**data})).invoke({'inputs':{},'node_outputs':{}})
    assert len(result['node_outputs']['outer']['items'])==2
    leaves=[e for e in events if e['type']=='node_completed' and e['node_id']=='start']
    assert len(leaves)==4
    assert all(e['scope'].count('/')==3 for e in leaves)
    assert len({e['invocation_id'] for e in leaves})==4


def test_missing_runtime_input_has_failed_node_event():
    workflow=WorkflowDefinition.model_validate({'id':'missing','kind':'online','nodes':[
        {'id':'start','type':'start','label':'Start'},
        {'id':'consumer','type':'passthrough','label':'Consumer','inputs':{'value':{'node_id':'start','output':'absent'}}}],
        'edges':[{'source':'start','target':'consumer'}]})
    events=[]
    with pytest.raises(ValueError):
        compile_workflow(workflow,emit=lambda event,**data:events.append({'type':event,**data})).invoke({'inputs':{},'node_outputs':{}})
    assert any(e['type']=='node_failed' and e['node_id']=='consumer' for e in events)

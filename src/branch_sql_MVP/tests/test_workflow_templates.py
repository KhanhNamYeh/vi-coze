import sqlite3
from types import SimpleNamespace
from unittest.mock import patch
from src.branch_sql_MVP.workflow.templates import templates
from src.branch_sql_MVP.workflow.compiler import compile_workflow
from src.branch_sql_MVP.offline.schema_catalog import build_schema_catalog, write_schema_catalog


def test_templates_have_display_metadata_and_layered_positions():
    items = templates()
    assert len(items) == 8
    for item in items:
        assert item.name, f'{item.id} missing display name'
        assert item.description, f'{item.id} missing description'
    no_index = [item for item in items if not item.requires_index]
    assert [item.id for item in no_index] == ['P1-full']
    for item in items:
        positions = [(node.position['x'], node.position['y']) for node in item.nodes]
        assert len(positions) == len(set(positions)), f'{item.id} has overlapping node positions'
        levels = {x for x, _ in positions}
        assert max(x for x, _ in positions) < 285 * len(levels), f'{item.id} layout is not layered'


def test_evidence_filter_applies_token_budget_after_llm_selection():
    from src.branch_sql_MVP.workflow.nodes.domain import evidence_filter
    items = [{'id': f'business:{i}', 'kind': 'business', 'source': 'rules',
              'text': 'word ' * 400, 'score': 1.0} for i in range(3)]
    ids = [item['id'] for item in items]
    generous = evidence_filter({'items': items, 'selected_ids': ids}, {'token_budget': 5000})
    tight = evidence_filter({'items': items, 'selected_ids': ids}, {'token_budget': 120})
    assert len(tight['items']) < len(generous['items'])
    assert len(tight['text']) < len(generous['text'])
    assert tight['trace'], 'budget trace must explain what was dropped'


def test_merge_debugs_from_supplied_inputs_without_run_state():
    from src.branch_sql_MVP.workflow.nodes.domain import merge
    import pytest
    config = {'sources': ['answer_output', 'sql_output']}
    assert merge({'answer_output': {'answer': 'x'}}, config) == {'answer': 'x'}
    assert merge({}, config, state={'node_outputs': {'sql_output': {'sql': 'SELECT 1'}}}) == {'sql': 'SELECT 1'}
    with pytest.raises(ValueError, match='answer_output, sql_output'):
        merge({}, config, state={'node_outputs': {}})


def test_template_p1_executes_sql_and_answers_from_rows(tmp_path):
    database = tmp_path / 'demo.sqlite'
    with sqlite3.connect(database) as db:
        db.execute('CREATE TABLE orders(amount INTEGER)')
        db.executemany('INSERT INTO orders VALUES (?)', [(100000,), (250000,)])
    business = tmp_path / 'business.md'
    business.write_text('Revenue is SUM(orders.amount)', encoding='utf-8')
    schema = tmp_path / 'schema.json'
    write_schema_catalog(build_schema_catalog(database), schema)
    prompts=[]
    class Fake:
        def with_structured_output(self, schema, include_raw):
            return SimpleNamespace(invoke=lambda messages: {'parsed': {'sql':'SELECT SUM(amount) AS total FROM orders','confidence':.9,'assumptions':[]}, 'raw':None})
        def invoke(self, messages):
            prompts.append(messages[-1].content)
            assert '350000' in messages[-1].content
            return SimpleNamespace(content='Tổng doanh thu là 350000.',usage_metadata={})
    with patch('src.branch_sql_MVP.workflow.nodes.llm.build_model', return_value=Fake()):
        result=compile_workflow(templates()[0]).invoke({'inputs':{'question':'Tổng doanh thu?','evidence':'','database':str(database),'schema_catalog_path':str(schema),'business_path':str(business),'mode':'answer'},'node_outputs':{}})
    assert result['node_outputs']['output']['answer']=='Tổng doanh thu là 350000.'
    assert result['node_outputs']['output']['observation']['preview']==[[350000]]
    assert len(prompts)==1
    assert 'sql_output' not in result['node_outputs']

def test_repair_template_bounds_calls_and_uses_final_observation(tmp_path):
    from src.branch_sql_MVP.workflow.templates import repair_body
    from src.branch_sql_MVP.workflow.contracts import WorkflowDefinition
    database=tmp_path/'repair.sqlite'
    with sqlite3.connect(database) as db:
        db.execute('CREATE TABLE orders(amount INTEGER)')
        db.execute('INSERT INTO orders VALUES (10)')
    calls=[]
    class Fake:
        def with_structured_output(self, schema, include_raw):
            def invoke(messages):
                calls.append(messages[-1].content)
                return {'parsed':{'sql':'SELECT amount FROM orders','confidence':.8,'assumptions':[]},'raw':None}
            return SimpleNamespace(invoke=invoke)
    workflow=WorkflowDefinition.model_validate({'id':'repair_test','kind':'online','nodes':[{'id':'loop','type':'bounded_loop','label':'Repair','config':{'max_iterations':3,'body':repair_body({'execution':{},'max_repairs':2})},'inputs':{key:{'value':value} for key,value in {'database':str(database),'question':'amount','context':'orders(amount)','prediction':{'sql':'SELECT missing FROM orders'}}.items()}}]})
    with patch('src.branch_sql_MVP.workflow.nodes.llm.build_model', return_value=Fake()):
        result=compile_workflow(workflow).invoke({'inputs':{},'node_outputs':{}})['node_outputs']['loop']
    assert len(calls)==1
    assert len(result['iterations'])==2
    assert result['observation']['status']=='success'
    assert result['observation']['preview']==[[10]]

def test_offline_template_registers_real_dataset_and_failure_is_visible(tmp_path, monkeypatch):
    from src.branch_sql_MVP.data import import_dataset as importer
    from src.branch_sql_MVP.workflow.templates import offline_template
    monkeypatch.setattr(importer,'ROOT',tmp_path)
    database=tmp_path/'source.sqlite'
    with sqlite3.connect(database) as db:db.execute('CREATE TABLE orders(amount INTEGER)')
    document=tmp_path/'business.md';document.write_text('Orders amount in VND',encoding='utf-8')
    workflow=offline_template('new_data',str(database),str(document),indexed=False)
    output=compile_workflow(workflow).invoke({'inputs':{},'node_outputs':{}})['node_outputs']['register']['dataset']
    assert output['capabilities']=={'schema':True,'business':True,'event':True,'index':False,'graph':False}
    assert importer.datasets()[0]['id']=='new_data'
    assert (importer.workspace()/'new_data'/'events.json').is_file()

def test_adaptive_three_candidates_and_invalid_choice(tmp_path):
    from src.branch_sql_MVP.workflow.templates import make_template
    database=tmp_path/'adaptive.sqlite'
    with sqlite3.connect(database) as db:
        db.execute('CREATE TABLE orders(amount INTEGER)');db.execute('INSERT INTO orders VALUES (123)')
    business=tmp_path/'business.md';business.write_text('Revenue = sum(amount)',encoding='utf-8')
    schema=tmp_path/'schema.json';write_schema_catalog(build_schema_catalog(database),schema)
    seen=[]
    class Fake:
        def with_structured_output(self,schema,include_raw):
            def invoke(messages):
                seen.append(messages[-1].content)
                if schema['title']=='Route': parsed={'route':'full','candidate_count':3,'reason':'test'}
                elif schema['title']=='Choice': parsed={'candidate_id':'invalid'}
                else: parsed={'sql':'SELECT amount FROM orders','confidence':.8,'assumptions':[]}
                return {'parsed':parsed,'raw':None}
            return SimpleNamespace(invoke=invoke)
    original=next(t for t in templates() if t.id=='G1-adaptive')
    parameters=original.defaults['parameters'];parameters['route']['max_candidates']=3
    definition=make_template({'id':'G1-test','scenario':'G1','parameters':parameters})
    with patch('src.branch_sql_MVP.workflow.nodes.llm.build_model',return_value=Fake()):
        result=compile_workflow(definition).invoke({'inputs':{'database':str(database),'schema_catalog_path':str(schema),'business_path':str(business),'question':'amount?','evidence':'','difficulty':'unknown','mode':'sql_only'},'node_outputs':{}})
    assert len(result['node_outputs']['candidates']['items'])==3
    assert result['node_outputs']['selected']['observation']['status']=='success'
    assert len(seen)==5


def test_offline_cache_resume_and_source_change(tmp_path, monkeypatch):
    import json
    import pytest
    from src.branch_sql_MVP.data import import_dataset as importer
    from src.branch_sql_MVP.workflow.nodes.offline import stage
    monkeypatch.setattr(importer,'ROOT',tmp_path)
    database=tmp_path/'source.sqlite'
    with sqlite3.connect(database) as db:db.execute('CREATE TABLE orders(amount INTEGER)')
    business=tmp_path/'source.md';business.write_text('Revenue is sum(amount)',encoding='utf-8')
    inputs={'name':'resume_test','database':str(database),'business':str(business)}
    validated=stage(inputs,{'stage':'validate'})
    prepared=stage(validated,{'stage':'preprocess'})
    schema=stage(prepared,{'stage':'schema'})
    stage(schema,{'stage':'event'})
    assert stage(inputs,{'stage':'validate'})['reused']
    assert stage(validated,{'stage':'preprocess'})['reused']
    # An unrelated later artifact must not invalidate preprocessing.
    (importer.workspace()/'resume_test'/'events.json').write_text('{}',encoding='utf-8')
    assert stage(validated,{'stage':'preprocess'})['reused']
    status=json.loads((importer.workspace()/'resume_test'/'offline-status.json').read_text(encoding='utf-8'))
    assert status['stages']['preprocess']['reused']
    business.write_text('Changed source',encoding='utf-8')
    with pytest.raises(ValueError,match='Business source changed'):
        stage(inputs,{'stage':'validate'})
    status=json.loads((importer.workspace()/'resume_test'/'offline-status.json').read_text(encoding='utf-8'))
    assert status['status']=='failed'


def test_small_linking_nodes_preserve_original_context(tmp_path,monkeypatch):
    from src.branch_sql_MVP.online import context_builder as original
    from src.branch_sql_MVP.workflow.templates import Builder, context
    from src.branch_sql_MVP.settings import load_settings
    database=tmp_path/'linking.sqlite'
    with sqlite3.connect(database) as db:
        db.execute('CREATE TABLE orders(amount INTEGER, status TEXT)')
        db.execute("INSERT INTO orders VALUES (100000,'paid')")
    schema=tmp_path/'schema.json';write_schema_catalog(build_schema_catalog(database),schema)
    monkeypatch.setattr(original,'retrieve_hybrid_evidence',lambda *a,**k:[{'id':'business:one','kind':'business',
        'text':'Revenue is sum(amount)','source':'rules','score':1,'metadata':{}}])
    settings=load_settings();parameters={'table_k':2,'value_k':3,'token_budget':5000}
    expected=original.build_linked_context('paid orders amount','status=paid',schema,
        knowledge_id='shop',doc_id='rules',settings=settings,parameters=parameters)
    b=Builder('linking_parity');b.node('start','start');entry,last=context(b,'context','linked',parameters);b.edge('start',entry)
    graph=compile_workflow(b.build({}),settings=settings)
    output=graph.invoke({'inputs':{'question':'paid orders amount','evidence':'status=paid','schema_catalog_path':str(schema),
        'knowledge_id':'shop','doc_id':'rules'},'node_outputs':{}})['node_outputs'][last]
    assert (output['text'],output['items'],output['trace'])==expected
    assert {n['type'] for n in b.nodes}>={'schema_link','value_link','retrieval','example_retrieval','context_builder'}

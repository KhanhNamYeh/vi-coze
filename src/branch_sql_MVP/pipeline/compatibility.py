"""Benchmark compatibility without a second graph implementation."""
import json
from pathlib import Path
from types import SimpleNamespace
from ..workflow.templates import make_template
from ..workflow.compiler import compile_workflow
from ..settings import ROOT
from .contracts import SQLPrediction

class LegacyWorkflow:
    def __init__(self,scenario,settings,provider=None,model=None,api_key=None):
        self.scenario=scenario;self.settings=settings.model_copy(deep=True)
        if provider:self.settings.api.provider=provider
        if model:self.settings.api.model=model
        self.api_key=api_key;self.states={}
    def definition(self,state=None):
        state=state or {}
        rows=json.loads((ROOT/'pipeline/presets.json').read_text(encoding='utf-8'))
        preset=next(row for row in rows if row['scenario']==self.scenario)
        p=preset['parameters']
        for old,new in [('context_parameters','context'),('execution_parameters','execution'),('route_parameters','route')]:
            if old in state:p[new]={**p[new],**state[old]}
        if 'max_repairs' in state:p['max_repairs']=state['max_repairs']
        return make_template({'id':'legacy-'+self.scenario,'scenario':self.scenario,'parameters':p})
    def inputs(self,state):
        return {**state,**state.get('context_parameters',{}),'database':state.get('database_path'),
                'evidence':state.get('evidence',''),'difficulty':state.get('difficulty','unknown'),'mode':state.get('mode','sql_only')}
    def adapt(self,result):
        values=result['node_outputs'];selected=values['selected'];candidates=[]
        if 'candidates' in values:candidates=values['candidates']['items']
        elif 'repair_loop' in values:candidates=[{**row['outputs'],'prediction':row['outputs']['observed_prediction'],'candidate_id':'candidate_'+str(index)} for index,row in enumerate(values['repair_loop']['iterations'])]
        else:candidates=[selected]
        candidates=[{**row,'strategy':row.get('candidate_id','default'),'prediction':SQLPrediction.model_validate(row['prediction']).model_dump(mode='json')} for row in candidates]
        return {'final_prediction':SQLPrediction.model_validate(selected['prediction']).model_dump(mode='json'),
          'selected_candidate_id':next((c['candidate_id'] for c in candidates if c['prediction']['sql']==SQLPrediction.model_validate(selected['prediction']).sql),selected['candidate_id']),'candidates':candidates,
          'observations':[{**row['observation'],'candidate_id':row['candidate_id']} for row in candidates if row.get('observation')],
          'repair_count':max(0,len(values.get('repair_loop',{}).get('iterations',[]))-1),
          'route':values.get('router',{}).get('json',{}).get('route'),
          'trajectory':[{'node':row['node_id'],'invocation_id':key,'output':row['output']} for key,row in result.get('invocations',{}).items()],
          'node_outputs':values,'invocations':result.get('invocations',{}),
          'answer':values.get('output',{}).get('answer')}
    def invoke(self,state,config=None):
        graph=compile_workflow(self.definition(state),settings=self.settings,api_key=self.api_key)
        result=graph.invoke({'inputs':self.inputs(state),'node_outputs':{}},config)
        adapted=self.adapt(result);self.states[(config or {}).get('configurable',{}).get('thread_id','default')]=adapted
        return adapted
    def stream(self,state,config=None,stream_mode=None):
        graph=compile_workflow(self.definition(state),settings=self.settings,api_key=self.api_key)
        outputs={};invocations={}
        for mode,chunk in graph.stream({'inputs':self.inputs(state),'node_outputs':{}},config,stream_mode=['updates','tasks']):
            if mode=='updates':
                for update in chunk.values():
                    outputs.update(update.get('node_outputs',{}));invocations.update(update.get('invocations',{}))
            yield mode,chunk
        adapted=self.adapt({'node_outputs':outputs,'invocations':invocations})
        self.states[(config or {}).get('configurable',{}).get('thread_id','default')]=adapted
    def get_state(self,config):
        return SimpleNamespace(values=self.states[config.get('configurable',{}).get('thread_id','default')])
    def get_graph(self):
        return compile_workflow(self.definition(),settings=self.settings).get_graph()

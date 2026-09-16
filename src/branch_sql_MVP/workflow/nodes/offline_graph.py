"""GraphRAG deterministic stages; extraction and reports are visible LLM instances."""
import json
from pathlib import Path
from ...offline import graph as business
from ...offline.chunk import load_chunks
from ...settings import GraphSettings
from ...data import import_dataset as importer
from ..store import atomic_write


def app_for(inputs, settings):
    root=importer.workspace()/inputs['name']
    app=settings.model_copy(deep=True)
    app.paths=app.paths.model_copy(update={'markdown':str(root/'markdown'),'artifacts':str(root/'artifacts')})
    return app


def graph_prepare(inputs, config, *, settings=None, **kwargs):
    app=app_for(inputs,settings)
    cfg=GraphSettings.model_validate({**app.graph.model_dump(),**config})
    chunks=load_chunks(inputs['doc_id'],settings=app)
    if cfg.max_chunks:chunks=chunks[:cfg.max_chunks]
    return {**inputs,'chunks':chunks,'graph_config':cfg.model_dump(mode='json')}


def graph_resolve(inputs, config, **kwargs):
    cfg=GraphSettings.model_validate(inputs['graph_config'])
    extractions=[(row['chunk_id'],'docs',business.ExtractedGraph.model_validate(row['extraction'])) for row in inputs['extractions']]
    nodes,edges,resolution=business._resolve(extractions,cfg)
    if not nodes:raise ValueError('Graph has no entities')
    graph,communities=business._communities(nodes,edges,cfg)
    items=[{'id':c['id'],'context':business._community_context(c,nodes,edges)} for c in communities[:cfg.max_reports]] if cfg.generate_reports else []
    return {**inputs,'nodes':nodes,'edges':edges,'communities':communities,'report_items':items,'resolution':resolution}


def graph_write(inputs,config,*,settings=None,**kwargs):
    app=app_for(inputs,settings);doc_id=inputs['doc_id'];by_id={n['id']:n for n in inputs['nodes']};by_community={c['id']:c for c in inputs['communities']}
    reports=[]
    for row in inputs['summaries']:
        summary=business.CommunitySummary.model_validate(row['summary']);community=by_community[row['community_id']];members=[by_id[key] for key in community['node_ids']]
        reports.append({'id':business._id('report',doc_id,community['id']),'community_id':community['id'],'title':summary.title,'text':summary.summary,'node_ids':community['node_ids'],
          'source_chunk_ids':list(dict.fromkeys(key for n in members for key in n['source_chunk_ids'])), 'source_kinds':list(dict.fromkeys(kind for n in members for kind in n['source_kinds']))})
    data={'doc_id':doc_id,'kind':'docs','agent':'shared_workflow_llm','method':'llm','parameters':inputs['graph_config'],
      'nodes':inputs['nodes'],'edges':inputs['edges'],'communities':inputs['communities'],'reports':reports,
      'stats':{**inputs['resolution'],'nodes':len(inputs['nodes']),'edges':len(inputs['edges']),'reports':len(reports)},'errors':{'chunks':[],'reports':[]}}
    path=app.path(app.paths.artifacts)/f'{doc_id}.graph.json'
    atomic_write(path,json.dumps(data,ensure_ascii=False,indent=2))
    # Subsequent embedding receives only artifact references and stage inputs.
    return {k:v for k,v in {**inputs,'graph_path':str(path),'graph_enabled':True}.items() if k not in {'chunks','extractions','nodes','edges','communities','report_items','summaries'}}

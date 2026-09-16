"""Offline stage adapters with validated artifact caches and dataset registration."""
from pathlib import Path
from hashlib import sha256
import json
import shutil
from threading import RLock
from ...data import import_dataset as importer
from ...settings import load_settings
from ..store import atomic_write

_LOCK = RLock()

def digest(path):
    h=sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''):
            h.update(block)
    return h.hexdigest()

def stage(inputs, config, *, settings=None, **kwargs):
    from ...offline import pipeline, extract, link, chunk, embed, index
    from ...offline.schema_catalog import build_schema_catalog, write_schema_catalog
    from ...offline.event_index import build_event_index, write_event_index
    name=inputs['name']; operation=config['stage']
    import re
    if not re.fullmatch(r'[a-z][a-z0-9_]{0,63}', name):
        raise ValueError('Invalid dataset name')
    root=importer.workspace()/name
    root.mkdir(parents=True,exist_ok=True)
    app=(settings or load_settings()).model_copy(deep=True)
    app.paths=app.paths.model_copy(update={'markdown':str(root/'markdown'),'artifacts':str(root/'artifacts')})
    app=importer.dataset_settings({'knowledge_id':'studio_'+name},app)
    app.graph=app.graph.model_copy(update={"enabled":bool(inputs.get("graph_enabled",False))})
    # Every adapter receives the frozen run settings; per-node overrides are validated.
    from ...settings import Settings
    patch=config.get('settings',{})
    values=app.model_dump()
    for key,value in patch.items():
        values[key]={**values[key],**value}
    app=Settings.model_validate(values)
    status_path=root/'offline-status.json'
    with _LOCK:
        if (root/'dataset.json').exists():
            raise FileExistsError('Dataset ready; import a new version name')
        status=json.loads(status_path.read_text(encoding='utf-8')) if status_path.exists() else {'id':name,'stages':{}}
        status['status']='running'
        status['current_stage']=operation
        atomic_write(status_path,json.dumps(status,ensure_ascii=False,indent=2))
        cache=root/'cache'/f'{operation}.json'
        # Include actual upstream artifact digests, so changed/missing files invalidate reuse.
        source_files={}
        for key in ('database','business','markdown_path','schema_path','event_path'):
            if inputs.get(key) and Path(inputs[key]).is_file():source_files[key]=digest(inputs[key])
        relevant={'validate':[], 'preprocess':['preprocess'],'schema':[], 'event':[],
                  'extract':[], 'link':[], 'chunk':['chunk'], 'embed':['embedding'], 'index':['index']}[operation] if operation!='register' else []
        fingerprint=sha256(json.dumps({'inputs':{k:v for k,v in inputs.items() if k!='reused'},'files':source_files,'settings':{key:values[key] for key in relevant},'config':config},sort_keys=True,default=str).encode()).hexdigest()
        if cache.exists() and operation not in {'index','register'}:
            old=json.loads(cache.read_text(encoding='utf-8'))
            if old['fingerprint']==fingerprint and all(Path(p).is_file() and digest(p)==h for p,h in old['artifacts'].items()):
                status['stages'][operation] = {'status':'completed', 'reused':True,
                    'fingerprint':fingerprint, 'artifacts':old['artifacts']}
                status.pop('error', None)
                atomic_write(status_path,json.dumps(status,ensure_ascii=False,indent=2))
                return {**old['output'],'reused':True}
        try:
            before = {str(p):digest(p) for p in root.rglob('*') if p.is_file() and 'cache' not in p.parts and p.name not in {'offline-status.json','dataset.json'}}
            output={**inputs};output.pop('reused',None)
            output["upstream_fingerprint"] = fingerprint
            if operation=='validate':
                build_schema_catalog(Path(inputs['database']))
                target=root/'database.sqlite'
                if (root/'dataset.json').exists():
                    raise FileExistsError('Dataset ready; import a new version name')
                if not target.exists():shutil.copy2(inputs['database'],target)
                elif digest(target)!=digest(inputs['database']):raise ValueError('Source changed; use a new dataset name')
                output['database']=str(target)
                document=root/(name+'_business'+Path(inputs['business']).suffix.lower())
                if not document.exists():shutil.copy2(inputs['business'],document)
                elif digest(document)!=digest(inputs['business']):raise ValueError('Business source changed; use a new dataset name')
                output['business']=str(document)
            elif operation=='preprocess':
                prepared=pipeline.preprocess(inputs['business'],settings=app)
                shutil.copy2(prepared['path'],root/'business.md')
                output.update(doc_id=prepared['doc_id'],markdown_path=prepared['path'],business=str(root/'business.md'))
            elif operation=='schema':
                catalog=build_schema_catalog(Path(inputs['database']))
                write_schema_catalog(catalog,root/'schema.json');output['schema_path']=str(root/'schema.json')
            elif operation=='event':
                catalog=json.loads(Path(inputs['schema_path']).read_text(encoding='utf-8'))
                write_event_index(build_event_index(catalog,Path(inputs['business'])),root/'events.json');output['event_path']=str(root/'events.json')
            elif operation=='extract':
                extract.run(inputs['markdown_path'],settings=app)
            elif operation=='link':link.run(inputs['doc_id'],settings=app)
            elif operation=='chunk':chunk.run(inputs['doc_id'],settings=app)
            elif operation=='embed':embed.run(inputs['doc_id'],settings=app)
            elif operation=='index':
                # Every artifact/config revision gets a new collection. Never delete
                # an existing index when a failed import resumes with changed chunks.
                knowledge='studio_'+name
                collection_names={kind:f'{knowledge}__{kind}_{fingerprint[:16]}' for kind in ('docs','sql','graph')}
                app.index=app.index.model_copy(update={'collections':{**app.index.collections,knowledge:collection_names}})
                output['collections']=collection_names
                indexed=index.run(inputs['doc_id'],kind='docs',knowledge_id='studio_'+name,recreate=False,settings=app)
                collection=app.index.collection('studio_'+name,'docs')
                if not index.client(app).collection_exists(collection):raise RuntimeError('Index collection not ready')
                if index.client(app).count(collection, exact=True).count != indexed['points']:
                    raise RuntimeError('Index point count does not match current chunks')
                if app.graph.enabled:
                    graph_collection=indexed.get('graph_collection')
                    if not graph_collection or not indexed.get('graph_points') or index.client(app).count(graph_collection,exact=True).count!=indexed['graph_points']:
                        raise RuntimeError('Graph index is not ready')
                output['indexed']=True
            elif operation=='register':
                record={'id':name,'question':inputs.get('question',''),'doc_id':inputs['doc_id'],'knowledge_id':'studio_'+name,
                        'indexed':inputs.get('indexed',False),'collections':inputs.get('collections',{}),'revision':digest(inputs['database'])+digest(inputs['business']),
                        'capabilities':{'schema':True,'business':True,'event':True,'index':inputs.get('indexed',False),'graph':bool(inputs.get('graph_enabled',False))}}
                atomic_write(root/'dataset.json',json.dumps(record,ensure_ascii=False,indent=2));output['dataset']=record
            artifacts={str(p):digest(p) for p in root.rglob('*') if p.is_file() and p.suffix in {'.md','.sqlite','.json','.jsonl'} and 'cache' not in p.parts and p.name not in {'offline-status.json','dataset.json'}}
            artifacts = {p:h for p,h in artifacts.items() if before.get(p)!=h}
            # Preserve unchanged stage outputs when rebuilding a stale cache.
            if cache.exists():
                previous=json.loads(cache.read_text(encoding='utf-8'))
                for path in previous.get('artifacts', {}):
                    if Path(path).is_file(): artifacts[path]=digest(path)
            status.pop('error',None)
            # Cache each stage's produced files rather than copying large data into workflow state.
            atomic_write(cache,json.dumps({'fingerprint':fingerprint,'artifacts':artifacts,'output':output},ensure_ascii=False,indent=2))
            status['stages'][operation]={'status':'completed','fingerprint':fingerprint,'artifacts':artifacts}
            status['status']='ready' if operation=='register' else 'running'
            atomic_write(status_path,json.dumps(status,ensure_ascii=False,indent=2))
            return output
        except Exception as error:
            status.update(status='failed',error=str(error))
            status['stages'][operation]={'status':'failed','error':str(error)}
            atomic_write(status_path,json.dumps(status,ensure_ascii=False,indent=2))
            raise

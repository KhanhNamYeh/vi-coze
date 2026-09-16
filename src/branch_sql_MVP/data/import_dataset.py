"""Import SQLite và tài liệu nghiệp vụ độc lập với benchmark/eval."""
from __future__ import annotations

import argparse
import json
import re
import shutil
from pathlib import Path

from ..settings import ROOT, IndexSettings, load_settings


def workspace():
    return ROOT / '.runtime/studio/datasets'


def datasets():
    return [json.loads(p.read_text(encoding='utf-8')) for p in sorted(workspace().glob('*/dataset.json'))]


def dataset_settings(record, settings=None):
    app = settings or load_settings()
    knowledge = record['knowledge_id']
    if record.get('id') and (workspace()/record['id']/'artifacts').exists():
        app=app.model_copy(update={'paths':app.paths.model_copy(update={'artifacts':str(workspace()/record['id']/'artifacts'),'markdown':str(workspace()/record['id']/'markdown')})})
    return app.model_copy(update={'index': IndexSettings.model_validate({
        **app.index.model_dump(), 'local_path': str(ROOT / '.runtime/studio/qdrant'),
        'knowledge_id': knowledge, 'collections': {**app.index.collections, knowledge: {
            'docs': knowledge + '__docs', 'sql': knowledge + '__train_examples',
            'graph': knowledge + '__graph', **record.get('collections', {})}},
    }), 'graph': app.graph.model_copy(update={'enabled': bool(record.get('capabilities', {}).get('graph', False))})})


def import_dataset(name: str, database: Path, business: Path, *, question: str = 'Liệt kê dữ liệu.',
                   build_index: bool = False):
    from ..workflow.templates import offline_template
    from ..workflow.compiler import compile_workflow
    if not re.fullmatch(r'[a-z][a-z0-9_]{0,63}', name):
        raise ValueError('Invalid dataset name')
    if (workspace() / name).exists():
        raise FileExistsError(f'{name} already exists; choose a new version name')
    for source in (database,business):
        if not source.is_file():
            raise FileNotFoundError(source)
    definition=offline_template(name,str(database.resolve()),str(business.resolve()),question,build_index)
    result=compile_workflow(definition).invoke({'inputs':{},'node_outputs':{}})
    return result['node_outputs']['register']['dataset']


def main():
    import sys
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--name', required=True)
    parser.add_argument('--database', type=Path, required=True)
    parser.add_argument('--business', type=Path, required=True)
    parser.add_argument('--question', default='Liệt kê dữ liệu.')
    parser.add_argument('--index', action='store_true', help='Tạo embedding + Qdrant cho đủ 8 pipeline')
    args = parser.parse_args()
    print(json.dumps(import_dataset(args.name, args.database, args.business, question=args.question,
                                   build_index=args.index), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()


def available_datasets():
    """Studio imports plus configured repository sources; no eval history needed."""
    from .service import catalog
    from hashlib import sha256
    ready=datasets()
    ready_ids={row['id'] for row in ready}
    result=[{**row,'ready':True,'label':row['id']} for row in ready]
    for split in ('dev','test'):
        for name,source in catalog(split=split).discover().items():
            if not source.business_document or not (source.database or source.sql_dump):
                continue
            target='repo_'+split+'_'+re.sub('[^a-z0-9_]','_',name.lower())[:32]+'_'+sha256((split+':'+name).encode()).hexdigest()[:8]
            if target in ready_ids:
                continue
            result.append({'id':f'repo:{split}:{name}','label':f'{name} ({split})',
                'source':'repository','split':split,'name':name,'import_name':target,
                'question':'','indexed':False,'ready':False})
    return result

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
    return app.model_copy(update={'index': IndexSettings.model_validate({
        **app.index.model_dump(), 'local_path': str(ROOT / '.runtime/studio/qdrant'),
        'knowledge_id': knowledge, 'collections': {**app.index.collections, knowledge: {
            'docs': knowledge + '__docs', 'sql': knowledge + '__train_examples',
            'graph': knowledge + '__graph'}},
    }), 'graph': app.graph.model_copy(update={'enabled': False})})


def import_dataset(name: str, database: Path, business: Path, *, question: str = 'Liệt kê dữ liệu.',
                   build_index: bool = False):
    from ..offline.schema_catalog import build_schema_catalog, write_schema_catalog
    from ..offline.event_index import build_event_index, write_event_index
    from ..offline import pipeline

    if not re.fullmatch(r'[a-z][a-z0-9_]{0,63}', name):
        raise ValueError('Tên dataset dùng chữ thường, số, dấu _, bắt đầu bằng chữ (tối đa 64 ký tự).')
    for path in (database, business):
        if not path.is_file():
            raise FileNotFoundError(path)
    target = workspace() / name
    if target.exists():
        raise FileExistsError(f'{name} đã tồn tại; chọn tên mới để không ghi đè dataset.')
    catalog = build_schema_catalog(database.resolve())
    target.mkdir(parents=True)
    shutil.copy2(database, target / 'database.sqlite')
    copied_business = target / (name + '_business' + business.suffix.lower())
    shutil.copy2(business, copied_business)
    app = load_settings()
    prepared = pipeline.preprocess(copied_business, settings=app)
    shutil.copy2(prepared['path'], target / 'business.md')
    catalog = build_schema_catalog(target / 'database.sqlite')
    write_schema_catalog(catalog, target / 'schema.json')
    write_event_index(build_event_index(catalog, target / 'business.md'), target / 'events.json')
    record = {'id': name, 'question': question, 'knowledge_id': 'studio_' + name,
              'doc_id': prepared['doc_id'], 'indexed': False}
    if build_index:
        from ..offline import extract, link, chunk, embed, index
        settings = dataset_settings(record, app)
        extract.run(prepared['path'], settings=settings)
        link.run(record['doc_id'], settings=settings)
        chunk.run(record['doc_id'], settings=settings)
        embed.run(record['doc_id'], settings=settings)
        index.run(record['doc_id'], kind='docs', knowledge_id=record['knowledge_id'],
                  recreate=False, settings=settings)
        record['indexed'] = True
    (target / 'dataset.json').write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
    return record


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

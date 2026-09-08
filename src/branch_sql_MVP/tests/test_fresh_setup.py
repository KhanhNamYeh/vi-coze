"""Clone mới: không dataset cũ, không bundle eval, không model trả phí."""
import json
import sqlite3

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.branch_sql_MVP import settings
from src.branch_sql_MVP.app import studio
from src.branch_sql_MVP.data import import_dataset as importer
from src.branch_sql_MVP.pipeline import prompt_baseline


def test_import_and_run_without_eval_history(tmp_path, monkeypatch):
    original_root = settings.ROOT
    monkeypatch.setattr(settings, 'ROOT', tmp_path)
    monkeypatch.setattr(importer, 'ROOT', tmp_path)
    monkeypatch.setattr(studio, 'BUNDLE', tmp_path / 'missing-bundle.json')
    # Presets are code resources, not generated artifacts.
    assert (original_root / 'pipeline/presets.json').is_file()
    database = tmp_path / 'input.sqlite'
    with sqlite3.connect(database) as connection:
        connection.execute('CREATE TABLE orders (id INTEGER, amount REAL)')
        connection.execute('INSERT INTO orders VALUES (1, 100)')
    business = tmp_path / 'input.md'
    business.write_text('# Orders\nDoanh thu là tổng orders.amount.', encoding='utf-8')
    api = FastAPI()
    api.include_router(studio.router)
    client = TestClient(api)
    assert client.get('/studio/cases').json() == []
    assert len(client.get('/studio/pipelines').json()) == 8
    record = importer.import_dataset('shop', database, business, question='Tổng doanh thu?')
    assert not record['indexed']
    other = importer.import_dataset('shop_second', database, business)
    assert other['doc_id'] != record['doc_id']
    assert client.get('/studio/cases').json()[0]['id'] == 'dataset:shop'
    with pytest.raises(FileExistsError):
        importer.import_dataset('shop', database, business)

    class Prediction:
        def model_dump(self, **kwargs):
            return {'sql': 'SELECT SUM(amount) FROM orders'}

    monkeypatch.setattr(prompt_baseline, 'generate_sql_candidate', lambda *args, **kwargs: Prediction())
    response = client.post('/studio/run', json={'pipeline_id': 'P1-full', 'case_id': 'dataset:shop'})
    assert json.loads(response.text.splitlines()[-1])['type'] == 'complete', response.text
    assert client.post('/studio/run', json={'pipeline_id': 'B4-hybrid', 'case_id': 'dataset:shop'}).status_code == 422
    assert client.get('/studio/pipelines/P1-full/replay/dataset:shop').status_code == 404

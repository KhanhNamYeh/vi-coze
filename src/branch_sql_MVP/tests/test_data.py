from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.branch_sql_MVP.data import service
from src.branch_sql_MVP.data.catalog import DatasetCatalog
from src.branch_sql_MVP.data.database import build_sqlite_database, inspect_schema, query_readonly
from src.branch_sql_MVP.eval.benchmark import value_fingerprint
from src.branch_sql_MVP.offline.chunk import build as build_chunks
from src.branch_sql_MVP.offline.extract import extract
from src.branch_sql_MVP.offline.link import link
from src.branch_sql_MVP.preprocess.sql_parse import to_markdown
from src.branch_sql_MVP.settings import ChunkSettings, load_settings


class CatalogTests(unittest.TestCase):
    def test_data_root_contains_only_dev_and_test(self):
        root = Path('C:\\Users\\Khanh\\Documents\\vi-coze\\src\\branch_sql_MVP\\data')
        self.assertEqual({"dev", "test"}, {path.name for path in root.iterdir() if path.is_dir() and not path.name.startswith("__")})

    def test_test_split_contains_legacy_datasets(self):
        root = Path('C:\\Users\\Khanh\\Documents\\vi-coze\\src\\branch_sql_MVP\\data') / "test"
        datasets = DatasetCatalog(root).discover()
        self.assertEqual({"financial", "debit_card_specializing"}, set(datasets))
        self.assertTrue(all(dataset.complete for dataset in datasets.values()))
        self.assertTrue(all(dataset.sql_dump is not None for dataset in datasets.values()))

    def test_dev_split_contains_vietnamese_bird_datasets(self):
        root = Path('C:\\Users\\Khanh\\Documents\\vi-coze\\src\\branch_sql_MVP\\data') / "dev"
        datasets = DatasetCatalog(root).discover()
        self.assertEqual(11, len(datasets))
        self.assertTrue(all(dataset.complete for dataset in datasets.values()))
        self.assertTrue(all(dataset.database is not None for dataset in datasets.values()))

        cases = json.loads((root / "dev.json").read_text(encoding="utf-8"))
        self.assertEqual(1534, len(cases))
        self.assertEqual(
            {"question_id", "db_id", "question", "evidence", "SQL", "difficulty"},
            set(cases[0]),
        )

    def test_configured_default_is_dev_and_test_is_explicit(self):
        settings = load_settings()
        self.assertEqual("dev", settings.eval.split)
        self.assertEqual(11, len(service.catalog(settings).discover()))
        self.assertEqual(2, len(service.catalog(settings, split="test").discover()))
        self.assertIsNone(settings.index.local_path)

    @patch("src.branch_sql_MVP.data.service.preprocess")
    def test_dev_gold_is_not_prepared_as_retrieval_knowledge(self, preprocess):
        preprocess.return_value = {"doc_id": "business", "path": "temporary"}
        result = service.prepare_knowledge("financial", load_settings(), split="dev")
        self.assertEqual([], result["sql"])
        preprocess.assert_called_once()

    def test_fingerprint_changes_when_chunk_contract_changes(self):
        first = value_fingerprint({"artifact_version": 1, "child_max": 512})
        second = value_fingerprint({"artifact_version": 2, "child_max": 512})
        self.assertNotEqual(first, second)


class GoldSqlTests(unittest.TestCase):
    def test_gold_sql_becomes_sectioned_markdown(self):
        source = Path('C:\\Users\\Khanh\\Documents\\vi-coze\\src\\branch_sql_MVP\\data') / "test" / "gold" / "financial" / "basic.sql"
        markdown = to_markdown(source)
        self.assertIn("## Gold sample 117", markdown)
        self.assertIn("-- Query:", markdown)
        self.assertIn("-- Evidence:", markdown)
        self.assertIn("```sql", markdown)
        self.assertEqual(2, markdown.count("## Gold sample"))

    def test_gold_query_child_returns_full_atomic_parent(self):
        markdown = """# california_schools · sample

## Gold sample 1 · simple

-- Query: Ở Los Angeles, có bao nhiêu trường?
-- Evidence: Sử dụng County Name.
```sql
SELECT COUNT(CDSCode) FROM frpm WHERE `County Name` = 'Los Angeles';
```
"""
        ir = {
            "doc_id": "california_schools_sample__sql",
            "source": "sample.sql",
            "elements": link(extract(markdown)),
        }
        cfg = ChunkSettings(unit="character", child_min=1, child_max=20, child_overlap=0, parent_max=20)
        children, parents = build_chunks(ir, cfg, "")
        self.assertEqual(1, len(children))
        self.assertEqual(1, len(parents))
        self.assertEqual("Ở Los Angeles, có bao nhiêu trường?", children[0]["text"])
        self.assertEqual("retrieval_child", children[0]["chunk_role"])
        self.assertTrue(parents[0]["atomic"])
        self.assertIn("-- Query: Ở Los Angeles", parents[0]["text"])
        self.assertIn("-- Evidence: Sử dụng County Name.", parents[0]["text"])
        self.assertIn("SELECT COUNT(CDSCode)", parents[0]["text"])
        self.assertGreater(len(parents[0]["text"]), cfg.parent_max)

    def test_database_dump_is_not_treated_as_knowledge_examples(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "dump.sql"
            path.write_text("CREATE TABLE sample(id INTEGER);", encoding="utf-8")
            with self.assertRaises(ValueError):
                to_markdown(path)


class BusinessChunkTests(unittest.TestCase):
    def test_business_table_and_each_q_rule_are_atomic_chunks(self):
        rows = "\n".join(f"| `column_{index}` | mô tả {index} |" for index in range(30))
        markdown = f"""## Từ điển dữ liệu

### `frpm`

| Cột SQL | Mô tả |
|---|---|
{rows}

## Bằng chứng và quy tắc nghiệp vụ từ mẫu chuẩn

- **Q0**: Tỷ lệ miễn phí = `Free Meal Count (K-12)` / `Enrollment (K-12)`
- **Q1**: Tỷ lệ FRPM = `FRPM Count (K-12)` / `Enrollment (K-12)`
"""
        ir = {
            "doc_id": "california_schools_business__md",
            "source": "california_schools.md",
            "elements": link(extract(markdown)),
        }
        cfg = ChunkSettings(unit="character", child_min=1, child_max=20, child_overlap=0, parent_max=20)
        children, parents = build_chunks(ir, cfg, "")

        tables = [item for item in children if item["type"] == "business_table"]
        rules = [item for item in children if item["type"] == "business_rule"]
        self.assertEqual(1, len(tables))
        self.assertIn("### `frpm`", tables[0]["text"])
        self.assertIn("`column_29`", tables[0]["text"])
        self.assertGreater(len(tables[0]["text"]), cfg.child_max)
        self.assertEqual(["Q0", "Q1"], [item["section_id"] for item in rules])
        self.assertEqual(2, len(rules))
        self.assertEqual(len(children), len(parents))
        self.assertTrue(all(parent["atomic"] for parent in parents))


class DatabaseTests(unittest.TestCase):
    def test_build_schema_and_readonly_query(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            dump = root / "sample.sql"
            database = root / "sample.sqlite"
            dump.write_text(
                "BEGIN; CREATE TABLE item(id INTEGER PRIMARY KEY, name TEXT NOT NULL); "
                "INSERT INTO item VALUES (1, 'one'), (2, 'two'); COMMIT;",
                encoding="utf-8",
            )
            result = build_sqlite_database(dump, database)
            self.assertEqual(1, result["tables"])
            self.assertEqual("item", inspect_schema(database)[0]["name"])
            rows = query_readonly(database, "SELECT name FROM item ORDER BY id", limit=1)
            self.assertEqual([{"name": "one"}], rows["rows"])
            self.assertTrue(rows["truncated"])
            with self.assertRaises((ValueError, sqlite3.OperationalError)):
                query_readonly(database, "DELETE FROM item")


if __name__ == "__main__":
    unittest.main()

"""Application-facing operations that connect configured paths to datasets."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from ..offline.pipeline import preprocess
from ..settings import Settings, load_settings
from .catalog import Dataset, DatasetCatalog
from .database import build_sqlite_database, inspect_schema, query_readonly

DatasetSplit = Literal["dev", "test"]


def _split_root(app: Settings, split: DatasetSplit | None) -> Path:
    selected = split or app.eval.split
    return app.path(app.paths.dev if selected == "dev" else app.paths.test)


def catalog(settings: Settings | None = None, *, split: DatasetSplit | None = None) -> DatasetCatalog:
    app = settings or load_settings()
    return DatasetCatalog(_split_root(app, split))


def dataset(name: str, settings: Settings | None = None, *, split: DatasetSplit | None = None) -> Dataset:
    return catalog(settings, split=split).get(name)


def prepare_knowledge(
    name: str,
    settings: Settings | None = None,
    *,
    split: DatasetSplit | None = None,
) -> dict[str, object]:
    app = settings or load_settings()
    selected_split = split or app.eval.split
    selected = dataset(name, app, split=selected_split)
    if selected.business_document is None:
        raise FileNotFoundError(f"dataset '{name}' thiếu business document")
    documents = [preprocess(selected.business_document, settings=app)]
    examples = (
        [preprocess(path, settings=app) for path in selected.gold_examples]
        if selected_split == "test"
        else []
    )
    return {"dataset": name, "split": selected_split, "docs": documents, "sql": examples}


def database_path(
    name: str,
    settings: Settings | None = None,
    *,
    split: DatasetSplit | None = None,
) -> Path:
    app = settings or load_settings()
    selected = dataset(name, app, split=split)
    if selected.database is not None:
        return selected.database
    selected_split = split or app.eval.split
    return app.path(app.paths.runtime) / selected_split / "databases" / f"{name}.sqlite"


def build_database(
    name: str,
    *,
    overwrite: bool = False,
    settings: Settings | None = None,
    split: DatasetSplit | None = None,
) -> dict:
    app = settings or load_settings()
    selected = dataset(name, app, split=split)
    if selected.database is not None:
        if overwrite:
            raise ValueError("không được ghi đè SQLite nguồn của dataset")
        return {
            "path": str(selected.database),
            "size_bytes": selected.database.stat().st_size,
            "elapsed_seconds": 0.0,
            "tables": len(inspect_schema(selected.database)),
            "existing": True,
        }
    if selected.sql_dump is None:
        raise FileNotFoundError(f"dataset '{name}' thiếu SQL dump")
    return build_sqlite_database(
        selected.sql_dump,
        database_path(name, app, split=split),
        overwrite=overwrite,
    )


def schema(
    name: str,
    settings: Settings | None = None,
    *,
    split: DatasetSplit | None = None,
) -> list[dict[str, object]]:
    return inspect_schema(database_path(name, settings, split=split))


def query(
    name: str,
    sql: str,
    *,
    limit: int = 200,
    settings: Settings | None = None,
    split: DatasetSplit | None = None,
) -> dict[str, object]:
    return query_readonly(database_path(name, settings, split=split), sql, limit=limit)

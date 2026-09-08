"""Dataset discovery, preparation, and safe local SQL access."""

from .catalog import BenchmarkCase, Dataset, DatasetCatalog, load_benchmark_cases
from .database import build_sqlite_database, inspect_schema, query_readonly

__all__ = [
    "BenchmarkCase",
    "Dataset",
    "DatasetCatalog",
    "build_sqlite_database",
    "inspect_schema",
    "load_benchmark_cases",
    "query_readonly",
]

"""Command-line entry point for dataset and database operations."""

from __future__ import annotations

import argparse
import json
from typing import Any

from .data import service


def _print(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, default=str))


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(prog="kb-text2sql")
    actions = command.add_subparsers(dest="action", required=True)
    datasets = actions.add_parser("datasets", help="Liệt kê dataset theo split")
    datasets.add_argument("--split", choices=("dev", "test"), default=None)

    prepare = actions.add_parser("prepare", help="Chuẩn hóa business docs và gold SQL thành Markdown")
    prepare.add_argument("dataset")
    prepare.add_argument("--split", choices=("dev", "test"), default=None)

    build = actions.add_parser("build-db", help="Nạp SQL dump vào SQLite runtime")
    build.add_argument("dataset")
    build.add_argument("--overwrite", action="store_true")
    build.add_argument("--split", choices=("dev", "test"), default=None)

    schema = actions.add_parser("schema", help="Đọc schema của SQLite dataset")
    schema.add_argument("dataset")
    schema.add_argument("--split", choices=("dev", "test"), default=None)

    query = actions.add_parser("query", help="Chạy truy vấn chỉ đọc trên SQLite runtime")
    query.add_argument("dataset")
    query.add_argument("sql")
    query.add_argument("--limit", type=int, default=200)
    query.add_argument("--split", choices=("dev", "test"), default=None)
    return command


def main() -> None:
    import sys
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    arguments = parser().parse_args()
    if arguments.action == "datasets":
        result = service.catalog(split=arguments.split).list()
    elif arguments.action == "prepare":
        result = service.prepare_knowledge(arguments.dataset, split=arguments.split)
    elif arguments.action == "build-db":
        result = service.build_database(arguments.dataset, overwrite=arguments.overwrite, split=arguments.split)
    elif arguments.action == "schema":
        result = service.schema(arguments.dataset, split=arguments.split)
    else:
        result = service.query(arguments.dataset, arguments.sql, limit=arguments.limit, split=arguments.split)
    _print(result)


if __name__ == "__main__":
    main()

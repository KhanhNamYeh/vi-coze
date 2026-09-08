"""Chuẩn bị artifact, tune context trên dev và chạy workflow benchmark có resume."""

from __future__ import annotations

import hashlib
import json
import platform
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from statistics import fmean
from time import perf_counter
from typing import Any

from ..data.catalog import BenchmarkCase, load_benchmark_cases
from ..data.database import build_sqlite_database
from ..offline import chunk, embed, extract, index, link, pipeline
from ..offline.event_index import build_event_index, load_event_index, write_event_index
from ..offline.schema_catalog import build_schema_catalog, load_schema_catalog, write_schema_catalog
from ..online.context_builder import build_linked_context, estimate_tokens
from ..online.sag_retrieval import expand_event_neighborhood, retrieve_seed_events
from ..online.token_budget import TokenBudgetExceeded
from ..pipeline.contracts import RunManifest
from ..pipeline.registry import Scenario, build_workflow
from ..settings import IndexSettings, Settings, load_settings
from .text2sql import aggregate_results, evaluate_prediction, referenced_tables


def file_sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        while block := stream.read(8 * 1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def paths_fingerprint(paths: Iterable[str | Path]) -> str:
    digest = hashlib.sha256()
    for path in sorted({Path(value).resolve() for value in paths}, key=str):
        name = path.as_posix().encode("utf-8")
        digest.update(len(name).to_bytes(4, "big"))
        digest.update(name)
        with path.open("rb") as stream:
            while block := stream.read(8 * 1024 * 1024):
                digest.update(block)
    return digest.hexdigest()


def value_fingerprint(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def benchmark_settings(
    settings: Settings | None = None,
    *,
    qdrant_path: str | Path = ".runtime/text2sql_benchmark/qdrant",
    knowledge_id: str = "bird_benchmark",
) -> Settings:
    app = settings or load_settings()
    collections = {
        **app.index.collections,
        knowledge_id: {
            "docs": f"{knowledge_id}__docs",
            "sql": f"{knowledge_id}__train_examples",
            "graph": f"{knowledge_id}__legacy_graph",
        },
    }
    index_settings = IndexSettings.model_validate(
        {
            **app.index.model_dump(mode="json"),
            "knowledge_id": knowledge_id,
            "collections": collections,
            "local_path": str(Path(qdrant_path)),
        }
    )
    graph_settings = app.graph.model_copy(update={"enabled": False})
    return app.model_copy(update={"index": index_settings, "graph": graph_settings})


def _description_root(case: BenchmarkCase) -> Path | None:
    if case.split != "dev" or case.database is None:
        return None
    value = case.database.parent / "database_description"
    return value if value.is_dir() else None


def prepare_benchmark_artifacts(
    *,
    settings: Settings | None = None,
    runtime_root: str | Path = ".runtime/text2sql_benchmark",
    recreate: bool = False,
    value_limit: int = 8,
) -> tuple[Settings, dict[str, Any]]:
    root = Path(runtime_root).resolve()
    app = benchmark_settings(settings, qdrant_path=root / "qdrant")
    cases = {
        "dev": load_benchmark_cases(app.path(app.paths.dev), "dev"),
        "test": load_benchmark_cases(app.path(app.paths.test), "test"),
    }
    database_paths: dict[str, str] = {}
    schema_paths: dict[str, str] = {}
    event_paths: dict[str, str] = {}
    doc_ids: dict[str, str] = {}
    source_paths: set[Path] = set()
    first_index = True

    for split, split_cases in cases.items():
        for case in split_cases:
            source_paths.add(case.source)
            source_paths.add(case.business_document)
            if case.sql_dump:
                source_paths.add(case.sql_dump)
        by_database = {case.db_id: case for case in split_cases}
        for db_id, case in sorted(by_database.items()):
            key = f"{split}:{db_id}"
            if case.database is not None:
                database = case.database
            else:
                database = root / split / "databases" / f"{db_id}.sqlite"
                if recreate or not database.is_file():
                    build_sqlite_database(case.sql_dump, database, overwrite=database.exists())
            database_paths[key] = str(database.resolve())
            source_paths.add(database)

            schema_path = root / "schema" / split / f"{db_id}.schema.json"
            if recreate or not schema_path.is_file():
                catalog = build_schema_catalog(
                    database,
                    description_root=_description_root(case),
                    value_limit=value_limit,
                )
                write_schema_catalog(catalog, schema_path)
            else:
                catalog = load_schema_catalog(schema_path)
            schema_paths[key] = str(schema_path)

            event_path = root / "events" / split / f"{db_id}.events.json"
            current_event = load_event_index(event_path) if event_path.is_file() else {}
            if recreate or current_event.get("artifact_version") != 3:
                write_event_index(build_event_index(catalog, case.business_document), event_path)
            event_paths[key] = str(event_path)

            prepared = pipeline.preprocess(case.business_document, settings=app)
            doc_ids[key] = prepared["doc_id"]
            artifact_dir = app.path(app.paths.artifacts)
            vector_path = artifact_dir / f"{prepared['doc_id']}.vectors.jsonl"
            if recreate or not vector_path.is_file():
                extract.run(prepared["path"], settings=app)
                link.run(prepared["doc_id"], settings=app)
                chunk.run(prepared["doc_id"], settings=app)
                embed.run(prepared["doc_id"], settings=app)
            index.run(
                prepared["doc_id"],
                kind="docs",
                knowledge_id=app.index.knowledge_id,
                recreate=recreate and first_index,
                settings=app,
            )
            first_index = False

    artifact_sources = [*schema_paths.values(), *event_paths.values()]
    chunk_contract = {
        "artifact_version": 2,
        "settings": app.chunk.model_dump(mode="json"),
    }
    index_fingerprint = value_fingerprint(
        {
            "artifact_files": paths_fingerprint(artifact_sources),
            "chunk_contract": chunk_contract,
        }
    )
    artifact = {
        "runtime_root": str(root),
        "knowledge_id": app.index.knowledge_id,
        "database_paths": database_paths,
        "schema_paths": schema_paths,
        "event_paths": event_paths,
        "doc_ids": doc_ids,
        "dataset_fingerprint": paths_fingerprint(source_paths),
        "index_fingerprint": index_fingerprint,
        "chunk_contract": chunk_contract,
        "example_corpus": "unavailable: repository has no train split",
    }
    output = root / "artifacts.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(artifact, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return app, artifact


def _tables_from_items(items: list[dict[str, Any]], catalog: dict[str, Any]) -> set[str]:
    names = {table["name"].casefold(): table["name"] for table in catalog["tables"]}
    found: set[str] = set()
    for item in items:
        metadata = item.get("metadata", {})
        for field in ("table", "target_table"):
            value = str(metadata.get(field) or "").casefold()
            if value in names:
                found.add(value)
        text = str(item.get("text") or "").casefold()
        for normalized, original in names.items():
            if original.casefold() in text:
                found.add(normalized)
    return found


def score_linked_context(
    cases: list[BenchmarkCase],
    artifacts: dict[str, Any],
    settings: Settings,
    parameters: dict[str, Any],
) -> dict[str, Any]:
    started = perf_counter()
    recalls = []
    complete = []
    item_counts = []
    token_counts = []
    for case in cases:
        key = f"{case.split}:{case.db_id}"
        catalog = load_schema_catalog(artifacts["schema_paths"][key])
        context, items, _ = build_linked_context(
            case.question,
            case.evidence,
            artifacts["schema_paths"][key],
            knowledge_id=artifacts["knowledge_id"],
            doc_id=artifacts["doc_ids"][key],
            settings=settings,
            parameters=parameters,
        )
        gold = referenced_tables(case.gold_sql)
        predicted = _tables_from_items(items, catalog)
        recalls.append(len(gold & predicted) / max(len(gold), 1))
        complete.append(float(gold <= predicted))
        item_counts.append(len(items))
        token_counts.append(estimate_tokens(context))
    return {
        "cases": len(cases),
        "schema_table_recall": fmean(recalls),
        "schema_complete_rate": fmean(complete),
        "mean_evidence_items": fmean(item_counts),
        "mean_context_tokens": fmean(token_counts),
        "elapsed_seconds": perf_counter() - started,
    }


def score_relational_context(
    cases: list[BenchmarkCase],
    artifacts: dict[str, Any],
    settings: Settings,
    parameters: dict[str, Any],
) -> dict[str, Any]:
    started = perf_counter()
    recalls = []
    complete = []
    event_recalls = []
    event_complete = []
    event_counts = []
    for case in cases:
        key = f"{case.split}:{case.db_id}"
        catalog = load_schema_catalog(artifacts["schema_paths"][key])
        _, linked, _ = build_linked_context(
            case.question,
            case.evidence,
            artifacts["schema_paths"][key],
            knowledge_id=artifacts["knowledge_id"],
            doc_id=artifacts["doc_ids"][key],
            settings=settings,
            parameters=parameters,
        )
        event_index = load_event_index(artifacts["event_paths"][key])
        seeds = retrieve_seed_events(
            case.question,
            linked,
            event_index,
            top_k=int(parameters.get("event_top_k", 8)),
        )
        events = expand_event_neighborhood(
            seeds,
            event_index,
            hops=int(parameters.get("event_hops", 1)),
            node_budget=int(parameters.get("event_node_budget", 24)),
            token_budget=int(parameters.get("event_token_budget", 1800)),
        )
        gold = referenced_tables(case.gold_sql)
        predicted = _tables_from_items([*linked, *events], catalog)
        event_tables = _tables_from_items(events, catalog)
        recalls.append(len(gold & predicted) / max(len(gold), 1))
        complete.append(float(gold <= predicted))
        event_recalls.append(len(gold & event_tables) / max(len(gold), 1))
        event_complete.append(float(gold <= event_tables))
        event_counts.append(len(events))
    return {
        "cases": len(cases),
        "schema_table_recall": fmean(recalls),
        "schema_complete_rate": fmean(complete),
        "event_gold_table_recall": fmean(event_recalls),
        "event_gold_complete_rate": fmean(event_complete),
        "mean_event_items": fmean(event_counts),
        "elapsed_seconds": perf_counter() - started,
    }


def select_best_configuration(
    rows: list[dict[str, Any]],
    *,
    score_fields: tuple[str, ...] = ("schema_complete_rate", "schema_table_recall"),
) -> dict[str, Any]:
    if not rows:
        raise ValueError("không có kết quả dev để khóa cấu hình")
    return max(rows, key=lambda row: tuple(float(row.get(field, 0)) for field in score_fields))


def stratified_sample(cases: list[BenchmarkCase], per_database: int, seed: int = 42) -> list[BenchmarkCase]:
    import random

    randomizer = random.Random(seed)
    by_database: dict[str, list[BenchmarkCase]] = {}
    for case in cases:
        by_database.setdefault(case.db_id, []).append(case)
    selected = []
    for database_cases in by_database.values():
        ordered = sorted(database_cases, key=lambda case: (case.difficulty, case.question_id))
        randomizer.shuffle(ordered)
        selected.extend(ordered[:per_database])
    return sorted(selected, key=lambda case: case.stable_id)


def _usage_total(value: Any, field: str) -> int:
    if isinstance(value, dict):
        return int(value.get(field, 0) or 0) + sum(
            _usage_total(item, field) for key, item in value.items() if key != field
        )
    if isinstance(value, list):
        return sum(_usage_total(item, field) for item in value)
    return 0


def hardware_manifest() -> dict[str, Any]:
    import torch

    return {
        "platform": platform.platform(),
        "python": platform.python_version(),
        "torch": torch.__version__,
        "cuda_build": torch.version.cuda,
        "cuda_available": torch.cuda.is_available(),
        "device": torch.cuda.get_device_name(0) if torch.cuda.is_available() else "cpu",
    }


def run_scenario(
    cases: list[BenchmarkCase],
    *,
    scenario: Scenario,
    run_id: str,
    artifacts: dict[str, Any],
    settings: Settings,
    context_parameters: dict[str, Any],
    execution_parameters: dict[str, Any] | None = None,
    route_parameters: dict[str, Any] | None = None,
    max_repairs: int = 2,
    provider: str | None = None,
    model: str | None = None,
    api_key: str | None = None,
    max_concurrency: int = 2,
    resume: bool = True,
    progress: Callable[[int, int, str], None] | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if not cases:
        raise ValueError("run cần ít nhất một benchmark case")
    output_root = Path(artifacts["runtime_root"]) / "runs" / run_id
    output_root.mkdir(parents=True, exist_ok=True)
    rows_path = output_root / "cases.jsonl"
    existing: dict[str, dict[str, Any]] = {}
    if resume and rows_path.is_file():
        for line in rows_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                if not row.get("run_error"):
                    existing[row["stable_id"]] = row

    selected_provider = provider or settings.api.provider
    summary_path = output_root / "summary.json"
    if all(case.stable_id in existing for case in cases) and summary_path.exists():
        rows = [existing[case.stable_id] for case in cases]
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        metrics = aggregate_results(rows)
        metrics["input_tokens_all_calls"] = sum(int(row.get("total_input_tokens", 0)) for row in rows)
        metrics["output_tokens_all_calls"] = sum(int(row.get("total_output_tokens", 0)) for row in rows)
        return {**summary, "metrics": metrics}, rows
    selected_model = model or settings.api.model
    manifest = RunManifest(
        run_id=run_id,
        scenario=scenario,
        split=cases[0].split,
        model_provider=selected_provider,
        model=selected_model,
        prompt_version="bird-sql-v1",
        dataset_fingerprint=artifacts["dataset_fingerprint"],
        index_fingerprint=artifacts["index_fingerprint"],
        dependency_lock_sha256=file_sha256(Path(__file__).resolve().parents[3] / "uv.lock"),
        seed=42,
        hardware=hardware_manifest(),
        parameters={
            "context": context_parameters,
            "execution": execution_parameters or {},
            "route": route_parameters or {},
            "max_repairs": max_repairs,
            "max_concurrency": max_concurrency,
            "generation": settings.llm.model_dump(mode="json"),
            "example_corpus": artifacts["example_corpus"],
            "evaluation_protocol": "sqlite_result_equivalence_v1",
            "evaluation_error_policy": "gold execution failures are unscored; report coverage",
        },
    ).model_dump(mode="json")
    (output_root / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    graph = build_workflow(scenario, settings, provider=provider, model=model, api_key=api_key)

    def run_one(case: BenchmarkCase) -> dict[str, Any]:
        key = f"{case.split}:{case.db_id}"
        database_path = artifacts["database_paths"][key]
        parameters = {
            **context_parameters,
            "knowledge_id": artifacts["knowledge_id"],
            "doc_id": artifacts["doc_ids"][key],
        }
        state = {
            **case.workflow_input(database=Path(database_path)),
            "scenario": scenario,
            "schema_catalog_path": artifacts["schema_paths"][key],
            "event_index_path": artifacts["event_paths"][key],
            "context_parameters": parameters,
            "execution_parameters": execution_parameters or {},
            "route_parameters": route_parameters or {},
            "max_repairs": max_repairs,
            "candidates": [],
            "observations": [],
            "trajectory": [],
        }
        try:
            result = graph.invoke(
                state,
                {
                    "configurable": {"thread_id": f"{run_id}:{case.stable_id}"},
                    "recursion_limit": max(20, 8 + 4 * max_repairs),
                    "metadata": {"run_id": run_id, "scenario": scenario, "stable_id": case.stable_id},
                },
            )
            prediction = dict(result["final_prediction"])
            evaluation = evaluate_prediction(
                case,
                prediction,
                database_path,
                timeout_seconds=float((execution_parameters or {}).get("eval_timeout_seconds", 10.0)),
            )
            candidates = result.get("candidates", [])
            trajectory = result.get("trajectory", [])
            return {
                "stable_id": case.stable_id,
                "scenario": scenario,
                "db_id": case.db_id,
                "difficulty": case.difficulty,
                "prediction": prediction,
                "route": result.get("route"),
                "repair_count": result.get("repair_count", 0),
                "candidates": candidates,
                "observations": result.get("observations", []),
                "evidence_ids": [item["id"] for item in result.get("evidence_items", [])],
                "trajectory": trajectory,
                "total_input_tokens": _usage_total(candidates, "input_tokens")
                + _usage_total(trajectory, "input_tokens"),
                "total_output_tokens": _usage_total(candidates, "output_tokens")
                + _usage_total(trajectory, "output_tokens"),
                **evaluation,
            }
        except TokenBudgetExceeded:
            raise
        except Exception as error:
            return {
                "stable_id": case.stable_id,
                "scenario": scenario,
                "db_id": case.db_id,
                "difficulty": case.difficulty,
                "run_error": f"{type(error).__name__}: {error}",
            }

    pending = [case for case in cases if case.stable_id not in existing]
    completed = len(existing)
    budget_error = None
    if pending:
        with ThreadPoolExecutor(max_workers=max_concurrency) as executor:
            futures = {executor.submit(run_one, case): case for case in pending}
            with rows_path.open("a", encoding="utf-8", newline="\n") as stream:
                for future in as_completed(futures):
                    if future.cancelled():
                        continue
                    try:
                        row = future.result()
                    except TokenBudgetExceeded as error:
                        # Các case khác còn chạy sẽ kết thúc; không lưu case bị chặn là lỗi SQL.
                        for pending_future in futures:
                            pending_future.cancel()
                        budget_error = error
                        continue
                    existing[row["stable_id"]] = row
                    stream.write(json.dumps(row, ensure_ascii=False) + "\n")
                    stream.flush()
                    completed += 1
                    if progress:
                        progress(completed, len(cases), row["stable_id"])
    if budget_error is not None:
        raise budget_error
    rows = [existing[case.stable_id] for case in cases]
    metrics = aggregate_results(rows)
    metrics["input_tokens_all_calls"] = sum(int(row.get("total_input_tokens", 0)) for row in rows)
    metrics["output_tokens_all_calls"] = sum(int(row.get("total_output_tokens", 0)) for row in rows)
    summary = {"run_id": run_id, "scenario": scenario, "manifest": manifest, "metrics": metrics}
    (output_root / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return summary, rows

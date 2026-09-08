"""Dịch BIRD dev sang tiếng Việt mà không thay đổi SQL.

Checkpoint chỉ tồn tại trong thư mục tạm của tiến trình và bị xóa khi kết thúc.
Script không lưu translation summary hoặc SQL dump trùng với SQLite nguồn.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import os
import re
import sqlite3
import sys
import tempfile
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from google import genai
from google.genai import types

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "data" / "dev"
MODEL = "gemini-3.5-flash-lite"

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def load_env(path: Path) -> None:
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def estimate_tokens(text: str) -> int:
    """Conservative estimate used only for client-side TPM throttling."""
    return max(1, (len(text) + 2) // 3)


@dataclass
class WindowEntry:
    at: float
    tokens: int


class MinuteLimiter:
    def __init__(self, rpm: int, tpm: int) -> None:
        if rpm < 1 or tpm < 1:
            raise ValueError("rpm và tpm phải lớn hơn 0")
        self.rpm = rpm
        self.tpm = tpm
        self.entries: deque[WindowEntry] = deque()

    def wait(self, tokens: int) -> None:
        while True:
            now = time.monotonic()
            while self.entries and now - self.entries[0].at >= 60:
                self.entries.popleft()
            used_tokens = sum(entry.tokens for entry in self.entries)
            if len(self.entries) < self.rpm and used_tokens + tokens <= self.tpm:
                self.entries.append(WindowEntry(now, tokens))
                return
            sleep_for = max(0.25, 60 - (now - self.entries[0].at) + 0.1)
            print(f"[quota] chờ {sleep_for:.1f}s (RPM={len(self.entries)}/{self.rpm}, TPM≈{used_tokens}/{self.tpm})")
            time.sleep(sleep_for)


class JsonlCheckpoint:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.items: dict[str, dict[str, Any]] = {}
        if path.is_file():
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    item = json.loads(line)
                    self.items[str(item["id"])] = item

    def add(self, item: dict[str, Any]) -> None:
        item_id = str(item["id"])
        if item_id in self.items:
            return
        with self.path.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(item, ensure_ascii=False) + "\n")
        self.items[item_id] = item


class GeminiTranslator:
    def __init__(self, api_key: str, model: str, rpm: int, tpm: int) -> None:
        self.client = genai.Client(api_key=api_key)
        self.model = model
        self.limiter = MinuteLimiter(rpm, tpm)
        self.request_count = 0
        self.input_tokens = 0
        self.output_tokens = 0

    @staticmethod
    def _extract_array(text: str) -> list[dict[str, Any]]:
        value = json.loads(text)
        if isinstance(value, dict) and isinstance(value.get("items"), list):
            value = value["items"]
        if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
            raise ValueError("Gemini không trả về JSON array hợp lệ")
        return value

    def translate(self, instruction: str, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        payload = json.dumps(items, ensure_ascii=False)
        prompt = f"""{instruction}

QUY TẮC BẮT BUỘC:
- Trả về duy nhất một JSON array, đúng số phần tử và đúng thứ tự đầu vào.
- Giữ nguyên trường id và tất cả SQL identifier, literal, mã, công thức, số, ngày tháng.
- Chỉ dịch các trường văn bản tiếng Anh được yêu cầu sang tiếng Việt tự nhiên, chính xác.
- Không giải thích, không thêm hoặc lược bỏ thông tin, không dùng Markdown fence.
- Chuỗi rỗng phải tiếp tục là chuỗi rỗng.

INPUT JSON:
{payload}
"""
        estimated = estimate_tokens(prompt)
        last_error: Exception | None = None
        for attempt in range(6):
            self.limiter.wait(estimated)
            try:
                response = self.client.models.generate_content(
                    model=self.model,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        temperature=0,
                        response_mime_type="application/json",
                    ),
                )
                result = self._extract_array(response.text or "")
                expected_ids = [str(item["id"]) for item in items]
                actual_ids = [str(item.get("id")) for item in result]
                if actual_ids != expected_ids:
                    raise ValueError(f"ID đầu ra không khớp: expected={expected_ids[:3]}, actual={actual_ids[:3]}")
                usage = response.usage_metadata
                self.request_count += 1
                self.input_tokens += int(getattr(usage, "prompt_token_count", 0) or 0)
                self.output_tokens += int(getattr(usage, "candidates_token_count", 0) or 0)
                return result
            except Exception as error:  # API errors differ between SDK releases.
                last_error = error
                if attempt == 5:
                    break
                delay = min(120, 5 * (2**attempt))
                print(f"[retry] {type(error).__name__}: {error}; chờ {delay}s")
                time.sleep(delay)
        assert last_error is not None
        raise last_error


def batches(items: list[dict[str, Any]], size: int) -> list[list[dict[str, Any]]]:
    return [items[start : start + size] for start in range(0, len(items), size)]


def translate_cases(
    source: list[dict[str, Any]],
    translator: GeminiTranslator,
    checkpoint: JsonlCheckpoint,
    batch_size: int,
) -> list[dict[str, Any]]:
    pending = [
        {"id": str(case["question_id"]), "question": case["question"], "evidence": case.get("evidence", "")}
        for case in source
        if str(case["question_id"]) not in checkpoint.items
    ]
    instruction = "Dịch question và evidence của bộ Text-to-SQL BIRD sang tiếng Việt."
    for number, batch in enumerate(batches(pending, batch_size), start=1):
        print(f"[questions] batch {number}/{max(1, len(batches(pending, batch_size)))} ({len(batch)} mục)")
        for item in translator.translate(instruction, batch):
            checkpoint.add(item)

    translated: list[dict[str, Any]] = []
    for case in source:
        item = checkpoint.items[str(case["question_id"])]
        translated.append({**case, "question": item["question"], "evidence": item["evidence"]})
    return translated


def translate_evidence(
    cases: list[dict[str, Any]],
    translator: GeminiTranslator,
    checkpoint: JsonlCheckpoint,
    batch_size: int,
) -> list[dict[str, Any]]:
    pending = [
        {"id": str(case["question_id"]), "evidence": case.get("evidence", "")}
        for case in cases
        if str(case.get("evidence", "")).strip() and str(case["question_id"]) not in checkpoint.items
    ]
    instruction = """Dịch TOÀN BỘ phần diễn giải tiếng Anh trong evidence sang tiếng Việt.
Các cụm như "refers to", "means", "denotes", "is calculated as", "corresponds to" bắt buộc phải dịch.
Chỉ giữ nguyên: tên bảng/cột/hàm SQL, biểu thức trong backtick, literal trong dấu nháy,
mã viết tắt, con số, ngày tháng và công thức. Không được giữ nguyên cả câu tiếng Anh chỉ vì câu có SQL identifier."""
    all_batches = batches(pending, batch_size)
    for number, batch in enumerate(all_batches, start=1):
        print(f"[evidence] batch {number}/{max(1, len(all_batches))} ({len(batch)} mục)")
        for item in translator.translate(instruction, batch):
            checkpoint.add(item)

    translated: list[dict[str, Any]] = []
    for case in cases:
        evidence = str(case.get("evidence", ""))
        if evidence.strip():
            evidence = str(checkpoint.items[str(case["question_id"])]["evidence"])
        translated.append({**case, "evidence": evidence})
    return translated


def schema_identifiers(tables_path: Path) -> dict[str, set[str]]:
    definitions = json.loads(tables_path.read_text(encoding="utf-8"))
    result: dict[str, set[str]] = {}
    for definition in definitions:
        values = set(definition.get("table_names_original", []))
        values.update(name for _, name in definition.get("column_names_original", []) if name != "*")
        result[str(definition["db_id"])] = {str(value) for value in values if str(value).strip()}
    return result


def sql_literals(sql: str) -> set[str]:
    strings = {value.replace("''", "'") for value in re.findall(r"'((?:''|[^'])*)'", sql)}
    numbers = set(re.findall(r"(?<![A-Za-z_])\d+(?:\.\d+)?(?![A-Za-z_])", sql))
    return {value for value in strings | numbers if value}


def mask_protected(text: str, protected: set[str], prefix: str) -> tuple[str, dict[str, str]]:
    spans: list[tuple[int, int]] = [(match.start(), match.end()) for match in re.finditer(r"`[^`]+`", text)]
    for value in sorted(protected, key=lambda item: (-len(item), item)):
        escaped = re.escape(value)
        if value[0].isalnum() or value[0] == "_":
            escaped = rf"(?<![\w]){escaped}"
        if value[-1].isalnum() or value[-1] == "_":
            escaped = rf"{escaped}(?![\w])"
        for match in re.finditer(escaped, text):
            candidate = (match.start(), match.end())
            if not any(candidate[0] < end and start < candidate[1] for start, end in spans):
                spans.append(candidate)
    spans.sort()
    mapping: dict[str, str] = {}
    parts: list[str] = []
    cursor = 0
    for index, (start, end) in enumerate(spans):
        marker = f"__{prefix}_KEEP_{index:03d}__"
        parts.extend([text[cursor:start], marker])
        mapping[marker] = text[start:end]
        cursor = end
    parts.append(text[cursor:])
    return "".join(parts), mapping


def contains_protected(text: str, value: str) -> bool:
    escaped = re.escape(value)
    if value[0].isalnum() or value[0] == "_":
        escaped = rf"(?<![\w]){escaped}"
    if value[-1].isalnum() or value[-1] == "_":
        escaped = rf"{escaped}(?![\w])"
    return re.search(escaped, text) is not None


def restore_protected(text: str, mapping: dict[str, str]) -> str:
    for marker, value in mapping.items():
        if marker not in text:
            raise ValueError(f"Gemini làm mất placeholder {marker}")
        text = text.replace(marker, value)
    if re.search(r"__[QE]_KEEP_\d+__", text):
        raise ValueError("Đầu ra còn placeholder không xác định")
    return text


def translate_localized_cases(
    source_cases: list[dict[str, Any]],
    identifiers: dict[str, set[str]],
    translator: GeminiTranslator,
    checkpoint: JsonlCheckpoint,
    batch_size: int,
) -> list[dict[str, Any]]:
    masked_items: list[dict[str, Any]] = []
    mappings: dict[str, dict[str, dict[str, str]]] = {}
    for case in source_cases:
        case_id = str(case["question_id"])
        if case_id in checkpoint.items:
            continue
        protected = identifiers[str(case["db_id"])] | sql_literals(str(case["SQL"]))
        question, question_map = mask_protected(str(case["question"]), protected, "Q")
        evidence, evidence_map = mask_protected(str(case.get("evidence", "")), protected, "E")
        masked_items.append({"id": case_id, "question": question, "evidence": evidence})
        mappings[case_id] = {"question": question_map, "evidence": evidence_map}

    instruction = """Dịch question và evidence của bộ Text-to-SQL BIRD sang tiếng Việt chuẩn xác.
Mọi token dạng __Q_KEEP_000__ hoặc __E_KEEP_000__ là placeholder bất biến: phải sao chép nguyên trạng,
đúng chính tả và đúng vị trí. Dịch toàn bộ lời diễn giải xung quanh placeholder."""
    all_batches = batches(masked_items, batch_size)
    for number, batch in enumerate(all_batches, start=1):
        print(f"[localized] batch {number}/{max(1, len(all_batches))} ({len(batch)} mục)")
        translated = translator.translate(instruction, batch)
        for item in translated:
            case_id = str(item["id"])
            source_item = next(source for source in batch if str(source["id"]) == case_id)
            for attempt in range(4):
                try:
                    item["question"] = restore_protected(str(item["question"]), mappings[case_id]["question"])
                    item["evidence"] = restore_protected(str(item["evidence"]), mappings[case_id]["evidence"])
                    break
                except ValueError as error:
                    if attempt == 3:
                        raise
                    print(f"[placeholder-retry] id={case_id}: {error}")
                    item = translator.translate(instruction, [source_item])[0]
            checkpoint.add(item)

    return [
        {
            **case,
            "question": checkpoint.items[str(case["question_id"])]["question"],
            "evidence": checkpoint.items[str(case["question_id"])]["evidence"],
        }
        for case in source_cases
    ]


def translate_field_fixes(
    source_cases: list[dict[str, Any]],
    translated_cases: list[dict[str, Any]],
    field: str,
    translator: GeminiTranslator,
    checkpoint: JsonlCheckpoint,
    batch_size: int,
    identifiers: dict[str, set[str]],
    fix_english_phrases: bool = False,
) -> list[dict[str, Any]]:
    by_id = {str(case["question_id"]): case for case in translated_cases}
    phrase_pattern = re.compile(
        r"\b(refers to|means|denotes|is calculated as|corresponds to|represents|indicates|"
        r"number of|percentage of|difference between)\b",
        re.IGNORECASE,
    )
    masked_items: list[dict[str, Any]] = []
    mappings: dict[str, dict[str, str]] = {}
    for source in source_cases:
        case_id = str(source["question_id"])
        current = str(by_id[case_id].get(field, ""))
        literals = sql_literals(str(source["SQL"]))
        missing = any(
            contains_protected(str(source.get(field, "")), value) and not contains_protected(current, value)
            for value in literals
        )
        has_english = fix_english_phrases and phrase_pattern.search(current) is not None
        if not missing and not has_english:
            continue
        if case_id in checkpoint.items:
            continue
        protected = literals | (identifiers[str(source["db_id"])] if field == "evidence" else set())
        masked, mapping = mask_protected(str(source.get(field, "")), protected, field[0].upper())
        masked_items.append({"id": case_id, field: masked})
        mappings[case_id] = mapping

    instruction = f"""Dịch trường {field} của bộ Text-to-SQL BIRD sang tiếng Việt tự nhiên và đầy đủ.
Mọi placeholder __{field[0].upper()}_KEEP_000__ là bất biến và phải được sao chép nguyên trạng.
Dịch hết lời diễn giải tiếng Anh; không dịch placeholder, không thêm hoặc lược bỏ thông tin."""
    all_batches = batches(masked_items, min(batch_size, 30))
    for number, batch in enumerate(all_batches, start=1):
        print(f"[{field}-fix] batch {number}/{max(1, len(all_batches))} ({len(batch)} mục)")
        translated = translator.translate(instruction, batch)
        for item in translated:
            case_id = str(item["id"])
            source_item = next(source for source in batch if str(source["id"]) == case_id)
            for attempt in range(4):
                try:
                    item[field] = restore_protected(str(item[field]), mappings[case_id])
                    break
                except ValueError as error:
                    if attempt == 3:
                        raise
                    print(f"[placeholder-retry] id={case_id}: {error}")
                    item = translator.translate(instruction, [source_item])[0]
            checkpoint.add(item)

    fixed = []
    for case in translated_cases:
        case_id = str(case["question_id"])
        fixed.append({**case, field: checkpoint.items.get(case_id, {}).get(field, case.get(field, ""))})
    return fixed


def read_schema_rows(database_root: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    description_root = database_root / "database_description"
    for csv_path in sorted(description_root.glob("*.csv")):
        raw = csv_path.read_bytes()
        try:
            decoded = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            decoded = raw.decode("cp1252")
        with io.StringIO(decoded, newline="") as stream:
            for index, row in enumerate(csv.DictReader(stream)):
                rows.append(
                    {
                        "id": f"{csv_path.stem}:{index}",
                        "table": csv_path.stem,
                        "original_column_name": row.get("original_column_name", ""),
                        "column_name": row.get("column_name", ""),
                        "column_description": row.get("column_description", ""),
                        "data_format": row.get("data_format", ""),
                        "value_description": row.get("value_description", ""),
                    }
                )
    return rows


def translate_schema(
    database_root: Path,
    translator: GeminiTranslator,
    checkpoint: JsonlCheckpoint,
    batch_size: int,
) -> list[dict[str, Any]]:
    rows = read_schema_rows(database_root)
    pending = [row for row in rows if row["id"] not in checkpoint.items]
    instruction = (
        "Dịch column_name, column_description và value_description sang tiếng Việt. "
        "Giữ nguyên table, original_column_name và data_format."
    )
    for number, batch in enumerate(batches(pending, batch_size), start=1):
        print(
            f"[schema:{database_root.name}] batch {number}/{max(1, len(batches(pending, batch_size)))} "
            f"({len(batch)} mục)"
        )
        for item in translator.translate(instruction, batch):
            checkpoint.add(item)
    return [checkpoint.items[row["id"]] for row in rows]


def markdown_cell(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return "—"
    return text.replace("|", "\\|").replace("\r\n", "<br>").replace("\n", "<br>")


def render_business(database: str, rows: list[dict[str, Any]], cases: list[dict[str, Any]]) -> str:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row["table"])].append(row)
    output = ["## Từ điển dữ liệu", ""]
    for table, table_rows in grouped.items():
        output.extend(
            [
                f"### `{table}`",
                "",
                "| Cột SQL | Tên nghiệp vụ | Mô tả | Kiểu/định dạng | Ý nghĩa giá trị |",
                "|---|---|---|---|---|",
            ]
        )
        for row in table_rows:
            output.append(
                "| "
                + " | ".join(
                    [
                        f"`{row['original_column_name']}`",
                        markdown_cell(row.get("column_name")),
                        markdown_cell(row.get("column_description")),
                        markdown_cell(row.get("data_format")),
                        markdown_cell(row.get("value_description")),
                    ]
                )
                + " |"
            )
        output.append("")
    output.extend(["## Bằng chứng và quy tắc nghiệp vụ từ mẫu chuẩn", ""])
    evidence_cases = [case for case in cases if str(case.get("evidence", "")).strip()]
    if evidence_cases:
        for case in evidence_cases:
            evidence = str(case["evidence"]).strip().replace("\r\n", " ").replace("\n", " ")
            output.append(f"- **Q{case['question_id']}**: {evidence}")
    else:
        output.append("- Không có bằng chứng bổ sung.")
    output.append("")
    return "\n".join(output)


def cluster_for(sql: str) -> str:
    normalized = sql.upper()
    if re.search(r"\b(STRFTIME|DATE|DATETIME|JULIANDAY)\s*\(", normalized) or "SUBSTR" in normalized:
        return "time_aggregation"
    if re.search(r"\(\s*SELECT\b|\bOVER\s*\(", normalized):
        return "subquery_topn"
    if "/" in sql and re.search(r"\b(COUNT|SUM|AVG)\s*\(", normalized):
        return "ratio_formula"
    if re.search(r"\bJOIN\b", normalized):
        return "joins"
    if re.search(r"\b(COUNT|SUM|AVG|MIN|MAX)\s*\(|\bGROUP\s+BY\b", normalized):
        return "aggregation"
    return "basic"


def one_line(value: Any) -> str:
    return str(value or "").replace("\r\n", " ").replace("\n", " ").strip()


def render_gold(database: str, cluster: str, cases: list[dict[str, Any]]) -> str:
    output = [
        "-- Source: BIRD Dev 2024-06-27",
        f"-- Database: {database}",
        f"-- Test-case cluster: {cluster}",
        f"-- Cases: {len(cases)}",
        "",
    ]
    for case in cases:
        output.extend(
            [
                f"-- [question_id={case['question_id']}] [difficulty={case.get('difficulty', 'unknown')}]",
                f"-- Query: {one_line(case['question'])}",
                f"-- Evidence: {one_line(case.get('evidence', ''))}",
                str(case["SQL"]).strip().rstrip(";") + ";",
                "",
            ]
        )
    return "\n".join(output)


def dump_sqlite(source: Path, destination: Path) -> None:
    if destination.is_file():
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(".sql.tmp")
    connection = sqlite3.connect(f"file:{source.as_posix()}?mode=ro", uri=True)
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as stream:
            for line in connection.iterdump():
                stream.write(line)
                stream.write("\n")
    finally:
        connection.close()
    temporary.replace(destination)


def render_outputs(
    source_root: Path,
    output_root: Path,
    cases: list[dict[str, Any]],
    schemas: dict[str, list[dict[str, Any]]],
    dump_databases: bool,
) -> None:
    output_root.mkdir(parents=True, exist_ok=True)
    (output_root / "dev.json").write_text(
        json.dumps(cases, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    by_database: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for case in cases:
        by_database[str(case["db_id"])].append(case)

    for database, database_cases in sorted(by_database.items()):
        business_path = output_root / "business" / f"{database}.md"
        business_path.parent.mkdir(parents=True, exist_ok=True)
        business_path.write_text(
            render_business(database, schemas[database], database_cases),
            encoding="utf-8",
            newline="\n",
        )

        clusters: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for case in database_cases:
            clusters[cluster_for(str(case["SQL"]))].append(case)
        for cluster, cluster_cases in sorted(clusters.items()):
            gold_path = output_root / "gold" / database / f"{cluster}.sql"
            gold_path.parent.mkdir(parents=True, exist_ok=True)
            gold_path.write_text(
                render_gold(database, cluster, cluster_cases),
                encoding="utf-8",
                newline="\n",
            )

        if dump_databases:
            sqlite_path = source_root / "dev_databases" / database / f"{database}.sqlite"
            dump_sqlite(sqlite_path, output_root / "sql" / f"{database}.sql")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--model", default=MODEL)
    parser.add_argument("--rpm", type=int, default=int(os.getenv("GEMINI_TRANSLATE_RPM", "5")))
    parser.add_argument("--tpm", type=int, default=int(os.getenv("GEMINI_TRANSLATE_TPM", "100000")))
    parser.add_argument("--batch-size", type=int, default=50)
    parser.add_argument("--write-sql-dumps", action="store_true")
    return parser.parse_args()


def main() -> None:
    load_env(ROOT / ".env")
    args = parse_args()
    api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("Thiếu GOOGLE_API_KEY hoặc GEMINI_API_KEY")

    source_root = args.source.resolve()
    output_root = args.output.resolve()
    source_cases = json.loads((source_root / "dev.json").read_text(encoding="utf-8"))
    translator = GeminiTranslator(api_key, args.model, args.rpm, args.tpm)
    with tempfile.TemporaryDirectory(prefix="bird_translate_") as temporary_directory:
        checkpoint_root = Path(temporary_directory)
        case_checkpoint = JsonlCheckpoint(checkpoint_root / "questions.jsonl")
        translated_cases = translate_cases(source_cases, translator, case_checkpoint, args.batch_size)
        evidence_checkpoint = JsonlCheckpoint(checkpoint_root / "evidence.jsonl")
        translated_cases = translate_evidence(translated_cases, translator, evidence_checkpoint, args.batch_size)
        identifiers = schema_identifiers(source_root / "dev_tables.json")
        question_fix_checkpoint = JsonlCheckpoint(checkpoint_root / "question_fixes.jsonl")
        translated_cases = translate_field_fixes(
            source_cases,
            translated_cases,
            "question",
            translator,
            question_fix_checkpoint,
            args.batch_size,
            identifiers,
        )
        evidence_fix_checkpoint = JsonlCheckpoint(checkpoint_root / "evidence_fixes.jsonl")
        translated_cases = translate_field_fixes(
            source_cases,
            translated_cases,
            "evidence",
            translator,
            evidence_fix_checkpoint,
            args.batch_size,
            identifiers,
            fix_english_phrases=True,
        )

        schemas: dict[str, list[dict[str, Any]]] = {}
        databases = sorted({str(case["db_id"]) for case in source_cases})
        for database in databases:
            checkpoint = JsonlCheckpoint(checkpoint_root / f"schema_{database}.jsonl")
            schemas[database] = translate_schema(
                source_root / "dev_databases" / database,
                translator,
                checkpoint,
                args.batch_size,
            )

        render_outputs(source_root, output_root, translated_cases, schemas, args.write_sql_dumps)
    summary = {
        "model": args.model,
        "configured_rpm": args.rpm,
        "configured_tpm": args.tpm,
        "requests_this_run": translator.request_count,
        "input_tokens_this_run": translator.input_tokens,
        "output_tokens_this_run": translator.output_tokens,
        "cases": len(translated_cases),
        "databases": len(databases),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

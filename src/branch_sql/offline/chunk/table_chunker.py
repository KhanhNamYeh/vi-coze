"""IR -> chunks. Chặng `chunk`.

    uv run python -m src.branch_sql.offline.chunk.table_chunker mo_ta_bang_bds_new__docx

Đọc `<doc_id>.linked.json` — KHÔNG đọc lại markdown, và KHÔNG đọc `.extract.json`:
element ở đó chưa có `section`/`table`, gom theo đơn vị sẽ ra rỗng.

Cắt theo THANG `chunk.split_on`, thứ tự trong mảng là thứ tự ưu tiên:

    heading      một heading cấp N = một đơn vị nội dung   (cắt theo cấu trúc)
    table_row    bảng quá dài -> từng nhóm hàng, lặp header
    length       chốt chặn cuối, RecursiveCharacterTextSplitter của LangChain

Chỉ xuống bậc sau khi bậc trước cho ra chunk vượt `budget.max`. Nhờ vậy tài liệu
có ranh giới rõ không bao giờ bị cắt giữa chừng, còn bảng khổng lồ vẫn không sinh
ra chunk quá dài cho embedder.

Ngân sách đếm bằng CHÍNH tokenizer của `embed.dense.model` khi `budget.unit` là
`token`. Đếm ký tự rồi nhân hệ số là đoán mò: tiếng Việt có dấu cho ra tỷ lệ
char/token khác hẳn định danh SQL viết hoa nằm ngay cạnh nó trong cùng một bảng.

Mỗi chunk giữ đường về IR: `element_ids` liệt kê phần tử đã ghép vào nó, nên truy
ngược ra số dòng trong `.md` là chuyện tra bảng.
"""

from __future__ import annotations

import json
import sys
from functools import lru_cache
from pathlib import Path

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from ...config import CHUNK, EMBED_MODEL, HEADING_ROLES, PROCESSED_DIR, listdir, rel
from ....schemas import ChunkMeta, context_prefix
from ..link.hierarchy import load_linked

# Vai trò của cấp heading sâu nhất = đơn vị chunk; cấp nông nhất = nhóm.
UNIT_ROLE = HEADING_ROLES[max(HEADING_ROLES)] if HEADING_ROLES else "table"
SECTION_ROLE = HEADING_ROLES[min(HEADING_ROLES)] if HEADING_ROLES else "section"


# ---- đo độ dài ------------------------------------------------------------

@lru_cache(maxsize=2)
def _tokenizer(model: str):
    from transformers import AutoTokenizer

    return AutoTokenizer.from_pretrained(model)


def measure(text: str, *, budget=None) -> int:
    """Độ dài của text theo đúng đơn vị mà profile khai."""
    budget = budget or CHUNK.budget
    if budget.unit == "char":
        return len(text)
    return len(_tokenizer(EMBED_MODEL).encode(text, add_special_tokens=False))


# ---- dựng text ------------------------------------------------------------

def common_prefix(names: list[str]) -> str:
    """Từ đầu tiên có mặt ở MỌI tên đơn vị -> nhãn phân loại, không phải tên.

    "Bảng V_USER_PRECINCT_PERMISSION", "Bảng PRECINCT", ... : "Bảng" xuất hiện ở
    cả 18 nên nó không phân biệt được cái nào với cái nào - đúng định nghĩa của
    một từ không mang thông tin. Cắt nó đi thì `table_name` còn lại đúng định
    danh SQL, thứ mà filter và BM25 cần khớp.

    Suy từ chính tập tên, nên không phải khai gì trong profile.
    """
    heads = [n.split(maxsplit=1) for n in names]
    if len(names) < 2 or any(len(h) < 2 for h in heads):
        return ""
    first = heads[0][0]
    return first if all(h[0] == first for h in heads) else ""


def render(el: dict, *, restore_labels: bool = True) -> str:
    """Một phần tử IR -> đoạn text đưa vào chunk.

    Dựng lại nhãn đã bị `strip_label` cắt: "Ý nghĩa của bảng:" là ngữ cảnh thật
    cho embedding, mất nó thì câu trở nên trơ trọi.
    """
    if el["modality"] == "heading":
        return f"{'#' * (el.get('level') or 1)} {el['text']}"

    label = el.get("label") if restore_labels else None
    if el["modality"] == "table":
        # Nhãn của bảng đứng riêng một dòng: "Chi tiết các cột trong bảng:" là
        # câu dẫn, dính vào hàng tiêu đề thì hỏng cú pháp bảng.
        return f"{label}\n{el['text']}" if label else el["text"]
    return f"{label} {el['text']}".strip() if label else el["text"]


def group_by_unit(elements: list[dict]) -> list[list[dict]]:
    """Gom phần tử theo đơn vị nội dung, giữ nguyên thứ tự đọc.

    Phần mở đầu của một nhóm (chưa thuộc đơn vị nào) bị bỏ - nó là câu dẫn,
    không phải nội dung của đơn vị nào cả.
    """
    groups: list[list[dict]] = []
    current: str | None = None

    for el in elements:
        is_unit_heading = el["modality"] == "heading" and el.get("role") == UNIT_ROLE
        owner = el["text"] if is_unit_heading else el.get(UNIT_ROLE)
        if not owner:
            continue
        if is_unit_heading or owner != current:
            groups.append([])
            current = owner
        groups[-1].append(el)
    return groups


# ---- thang cắt ------------------------------------------------------------

def _cell(text: str) -> str:
    """Escape dấu ngăn cột khi dựng lại hàng, nếu không ô chứa nó tạo cột giả."""
    return text.replace("|", "\\|")


def table_slices(el: dict, rule) -> list[str]:
    """Element table -> từng mảnh markdown, mỗi mảnh `rule.group` hàng.

    Dựng lại từ `columns`/`rows` mà `extract` đã tách, không parse lại markdown.
    Đổi lại thì căn lề của bảng gốc mất - chấp nhận được vì chỉ dựng lại khi
    bảng THẬT SỰ phải cắt; bảng vừa ngân sách dùng nguyên `el["text"]`.
    """
    columns, rows = el.get("columns") or [], el.get("rows") or []
    if not rows:
        return [el["text"]]

    header = [
        "| " + " | ".join(_cell(c) for c in columns) + " |",
        "| " + " | ".join("---" for _ in columns) + " |",
    ]
    out = []
    for i in range(0, len(rows), rule.group):
        body = [
            "| " + " | ".join(_cell(c) for c in row) + " |"
            for row in rows[i : i + rule.group]
        ]
        keep_header = rule.repeat_header or i == 0
        out.append("\n".join((header if keep_header else []) + body))
    return out


@lru_cache(maxsize=2)
def _length_splitter(max_len: int, overlap: int, unit: str):
    """Splitter của LangChain, đo bằng đúng đơn vị của ngân sách."""
    return RecursiveCharacterTextSplitter(
        chunk_size=max_len,
        chunk_overlap=overlap,
        length_function=len if unit == "char" else measure,
        separators=["\n\n", "\n", ". ", " ", ""],
    )


def split_unit(group: list[dict], cfg) -> list[tuple[str, list[dict]]]:
    """Một đơn vị nội dung -> các mảnh `(text, element đã dùng)`.

    Xuống bậc sau của thang CHỈ khi mảnh hiện tại còn vượt trần.
    """
    budget, rules = cfg.budget, cfg.split_on
    labels = cfg.context.restore_labels
    text = "\n".join(render(el, restore_labels=labels) for el in group).strip()

    if measure(text, budget=budget) <= budget.max or budget.on_overflow == "keep":
        return [(text, group)]

    # bậc table_row: tách văn xuôi khỏi bảng, cắt bảng theo nhóm hàng
    atomic = set(cfg.filter.atomic_modalities)
    row_rule = next((r for r in rules if r.by == "table_row"), None)
    tables = [el for el in group if el["modality"] == "table" and "table" not in atomic]
    parts: list[tuple[str, list[dict]]] = [(text, group)]

    if row_rule and tables:
        prose = [el for el in group if el["modality"] != "table"]
        head = "\n".join(render(el, restore_labels=labels) for el in prose).strip()
        sliced: list[tuple[str, list[dict]]] = []
        for el in tables:
            for i, piece in enumerate(table_slices(el, row_rule)):
                body = f"{head}\n{piece}" if i == 0 and head else piece
                sliced.append((body.strip(), prose + [el] if i == 0 else [el]))
        if sliced:
            parts = sliced
            if all(measure(p, budget=budget) <= budget.max for p, _ in parts):
                return parts

    # bậc length: chốt chặn cuối
    splitter = _length_splitter(budget.max, budget.overlap, budget.unit)
    out: list[tuple[str, list[dict]]] = []
    for piece, els in parts:
        out += [(p.strip(), els) for p in splitter.split_text(piece)]
    return out


# ---- điều phối ------------------------------------------------------------

def split(ir: dict, *, cfg=None) -> list[Document]:
    """IR -> list[Document]. Chỉ cắt, kiểm tra ở `check()`."""
    cfg = cfg or CHUNK
    doc_id, title = ir["doc_id"], ir.get("title", ir["doc_id"])
    inherit = cfg.context.inherit

    chunks: list[Document] = []
    per_section: dict[str | None, int] = {}

    groups = group_by_unit(ir["elements"])
    names = [
        g[0]["text"] if g[0]["modality"] == "heading" else g[0].get(UNIT_ROLE, "")
        for g in groups
    ]
    prefix = common_prefix(names)

    for group, name in zip(groups, names):
        section = group[0].get(SECTION_ROLE)
        per_section[section] = per_section.get(section, 0) + 1
        no = f"{len(per_section)}.{per_section[section]}"

        # Ngữ cảnh cho mảnh 2 trở đi: bảng bị cắt làm ba thì mảnh sau mất câu
        # "Ý nghĩa của bảng: ...", đứng một mình chỉ còn là lưới ô.
        carried = " ".join(
            el["text"] for el in group if el.get("role") in inherit.from_roles
        ).strip()[: inherit.max_chars]

        parts = split_unit(group, cfg)
        for i, (body, els) in enumerate(parts, 1):
            meta = ChunkMeta.build(
                text=body,
                doc_id=doc_id,
                section=section,
                table_name=name[len(prefix):].strip() if prefix else name.strip(),
                no=no,
                part=f"{i}/{len(parts)}",
                source_path=ir.get("source_name"),
                element_ids=[el["id"] for el in els],
                line_start=els[0].get("line_start"),
                line_end=els[-1].get("line_end"),
            )
            text = body if i == 1 or not carried else f"{carried}\n{body}"
            if cfg.context.breadcrumb.enabled:
                crumb = context_prefix(
                    title,
                    meta,
                    separator=cfg.context.breadcrumb.separator,
                    include_doc_title=cfg.context.breadcrumb.include_doc_title,
                )
                text = f"{crumb}\n{text}" if crumb else text
            if cfg.filter.drop_empty and not text.strip():
                continue
            meta = meta.with_rendered(text, n_tokens=measure(text, budget=cfg.budget))
            chunks.append(Document(page_content=text, metadata=meta.model_dump()))

    return chunks


def _size(meta: dict, unit: str) -> int:
    return meta["n_tokens"] if unit == "token" else meta["n_chars"]


def check(chunks: list[Document], *, cfg=None) -> list[str]:
    """Trả danh sách cảnh báo. Không tự sửa."""
    cfg = cfg or CHUNK
    budget = cfg.budget
    if not chunks:
        return [f"0 chunk - IR không có heading vai trò '{UNIT_ROLE}'"]

    warn: list[str] = []
    if over := [c for c in chunks if _size(c.metadata, budget.unit) > budget.max]:
        warn.append(
            f"{len(over)} chunk vượt trần {budget.max} {budget.unit} - "
            f"{', '.join(c.metadata['table_name'] for c in over[:3])}"
        )
    if under := [c for c in chunks if _size(c.metadata, budget.unit) < budget.min]:
        warn.append(
            f"{len(under)} chunk dưới sàn {budget.min} {budget.unit} - "
            f"{', '.join(c.metadata['table_name'] for c in under[:3])}"
        )

    seen: dict[str, str] = {}
    for c in chunks:
        h, name = c.metadata["content_hash"], c.metadata["table_name"]
        if h in seen:
            warn.append(f"{name} trùng nội dung với {seen[h]}")
        seen[h] = name
    return warn


def write_chunks(chunks: list[Document], *, out_dir: Path = PROCESSED_DIR, doc_id: str) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    dst = out_dir / f"{doc_id}.chunks.jsonl"
    with dst.open("w", encoding="utf-8") as f:
        for c in chunks:
            row = {"page_content": c.page_content, "metadata": c.metadata}
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return dst


def report(chunks: list[Document], warn: list[str], *, cfg=None) -> None:
    cfg = cfg or CHUNK
    if not chunks:
        print(f"     ! 0 chunk - IR không có heading vai trò '{UNIT_ROLE}'")
        return

    unit = cfg.budget.unit
    sizes = sorted(_size(c.metadata, unit) for c in chunks)
    pieces = sum(1 for c in chunks if c.metadata["part"] != "1/1")
    print(f"     {len(chunks)} chunk | min={sizes[0]} p50={sizes[len(sizes) // 2]} "
          f"max={sizes[-1]} {unit}")
    print(f"     có table_name: {sum(1 for c in chunks if c.metadata['table_name'])}"
          f"/{len(chunks)} | mảnh của đơn vị bị cắt: {pieces}")
    for w in warn:
        print(f"     ! {w}")


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        print(f"file có sẵn trong {rel(PROCESSED_DIR)}:")
        for n in listdir(PROCESSED_DIR, "*.linked.json"):
            print(f"  - {n.removesuffix('.linked.json')}")
        return 1

    doc_id = argv[0].removesuffix(".linked.json").removesuffix(".md")
    try:
        ir = load_linked(doc_id)
    except (FileNotFoundError, ValueError) as e:
        print(e, file=sys.stderr)
        return 1

    chunks = split(ir)
    warn = check(chunks)
    dst = write_chunks(chunks, doc_id=doc_id)

    print(f"{doc_id}.linked.json\n  -> {rel(dst)}")
    report(chunks, warn)
    return 1 if not chunks else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

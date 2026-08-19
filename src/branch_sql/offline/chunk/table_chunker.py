"""IR -> chunks. Chặng `chunk`.

    uv run python -m src.branch_sql.offline.chunk.table_chunker mo_ta_bang_bds_new__docx

Đọc `<doc_id>.linked.json` — KHÔNG đọc lại markdown, và KHÔNG đọc `.extract.json`:
element ở đó chưa có `section`/`table`, gom theo đơn vị sẽ ra rỗng.

Hai chế độ, theo đúng cách Dify chia:

    general       cắt phẳng, mọi chunk cùng một bộ tham số, khớp cái nào trả
                  thẳng cái đó. Một artifact: `.chunks.jsonl`.
    parent_child  hai tầng. CON nhỏ, đi vào vector store, dùng để khớp truy vấn.
                  CHA lớn, nằm ở `.parents.jsonl`, được trả về cho LLM khi con
                  khớp. Con mang `parent_chunk_id` trỏ về cha.

Trong mỗi tầng, cắt theo THANG `split_on`, thứ tự trong mảng là thứ tự ưu tiên:

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


def truncate(text: str, limit: int, *, budget) -> str:
    """Cắt cụt về đúng `limit` đơn vị. Chỉ `full_doc` dùng tới."""
    if budget.unit == "char":
        return text[:limit]
    tok = _tokenizer(EMBED_MODEL)
    return tok.decode(tok.encode(text, add_special_tokens=False)[:limit])


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


def render_all(elements: list[dict], *, restore_labels: bool = True) -> str:
    return "\n".join(render(el, restore_labels=restore_labels) for el in elements).strip()


def group_by_unit(elements: list[dict], *, unit_role: str | None = None) -> list[list[dict]]:
    """Gom phần tử theo đơn vị nội dung, giữ nguyên thứ tự đọc.

    Phần mở đầu của một nhóm (chưa thuộc đơn vị nào) bị bỏ - nó là câu dẫn,
    không phải nội dung của đơn vị nào cả.
    """
    unit_role = unit_role or UNIT_ROLE
    groups: list[list[dict]] = []
    current: str | None = None

    for el in elements:
        is_unit_heading = el["modality"] == "heading" and el.get("role") == unit_role
        owner = el["text"] if is_unit_heading else el.get(unit_role)
        if not owner:
            continue
        if is_unit_heading or owner != current:
            groups.append([])
            current = owner
        groups[-1].append(el)
    return groups


# ---- thang cắt ------------------------------------------------------------

NEWLINE = chr(10)


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
    # `overlap_rows` lặp N hàng cuối của mảnh trước vào đầu mảnh sau. Overlap
    # của bậc `length` đo bằng ký tự nên cắt ngang một hàng; ở đây đơn vị là
    # HÀNG nên mảnh sau luôn còn nguyên vài dòng ngữ cảnh phía trước.
    step = max(1, rule.group - max(0, rule.overlap_rows))
    out = []
    for i in range(0, len(rows), step):
        window = rows[i : i + rule.group]
        if not window:
            break
        body = [
            "| " + " | ".join(_cell(c) for c in row) + " |"
            for row in window
        ]
        keep_header = rule.repeat_header or i == 0
        out.append(NEWLINE.join((header if keep_header else []) + body))
        if i + rule.group >= len(rows):
            break
    return out


@lru_cache(maxsize=4)
def _length_splitter(max_len: int, overlap: int, unit: str, separators: tuple[str, ...]):
    """Splitter của LangChain, đo bằng đúng đơn vị của ngân sách.

    `keep_separator=False`: dấu ngăn bị xoá khỏi nội dung sau khi cắt, giống
    hành vi `Delimiter` của Dify.
    """
    return RecursiveCharacterTextSplitter(
        chunk_size=max_len,
        chunk_overlap=overlap,
        length_function=len if unit == "char" else measure,
        separators=list(separators),
        keep_separator=False,
    )


def split_unit(group: list[dict], layer, *, reserve: int = 0) -> list[tuple[str, list[dict]]]:
    """Một đơn vị nội dung -> các mảnh `(text, element đã dùng)`.

    `layer` là một ChunkCfg: ở chế độ general nó chính là cfg, ở parent-child
    thì tầng cha và tầng con là hai bản sao khác `split_on`/`budget`.
    Xuống bậc sau của thang CHỈ khi mảnh hiện tại còn vượt trần.

    `reserve` là chỗ để dành cho breadcrumb và ngữ cảnh thừa hưởng - hai thứ
    được ghép vào SAU khi cắt. Không trừ hao thì chunk cuối cùng vượt trần đúng
    bằng phần đầu đó, và embedder cắt cụt phần đuôi mà không báo gì.
    """
    budget, rules = layer.budget, layer.split_on
    labels = layer.context.restore_labels
    ceiling = max(budget.max - reserve, 1)
    text = render_all(group, restore_labels=labels)

    if measure(text, budget=budget) <= ceiling or budget.on_overflow == "keep":
        return [(text, group)]

    # bậc table_row: tách văn xuôi khỏi bảng, cắt bảng theo nhóm hàng
    atomic = set(layer.filter.atomic_modalities)
    row_rule = next((r for r in rules if r.by == "table_row"), None)
    tables = [el for el in group if el["modality"] == "table" and "table" not in atomic]
    parts: list[tuple[str, list[dict]]] = [(text, group)]

    if row_rule and tables:
        prose = [el for el in group if el["modality"] != "table"]
        head = render_all(prose, restore_labels=labels)
        sliced: list[tuple[str, list[dict]]] = []
        for el in tables:
            for i, piece in enumerate(table_slices(el, row_rule)):
                body = f"{head}\n{piece}" if i == 0 and head else piece
                sliced.append((body.strip(), prose + [el] if i == 0 else [el]))
        if sliced:
            parts = sliced
            if all(measure(p, budget=budget) <= ceiling for p, _ in parts):
                return parts

    # bậc length: chốt chặn cuối
    len_rule = next((r for r in rules if r.by == "length"), None)
    if len_rule is None:
        return parts
    splitter = _length_splitter(
        ceiling, budget.overlap, budget.unit, tuple(len_rule.separators)
    )
    out: list[tuple[str, list[dict]]] = []
    for piece, els in parts:
        out += [(p.strip(), els) for p in splitter.split_text(piece)]
    return out


# ---- điều phối ------------------------------------------------------------

def _unit_role(split_on) -> str:
    """Vai trò heading mà tầng này lấy làm đơn vị nội dung."""
    rule = next((r for r in split_on if r.by == "heading"), None)
    return HEADING_ROLES.get(rule.level, UNIT_ROLE) if rule else UNIT_ROLE


def _numbering():
    """`no` dạng `<thứ tự section>.<thứ tự đơn vị trong section>`."""
    per_section: dict[str | None, int] = {}

    def nxt(section: str | None) -> str:
        per_section[section] = per_section.get(section, 0) + 1
        return f"{len(per_section)}.{per_section[section]}"

    return nxt


def _emit(
    group: list[dict],
    *,
    ir: dict,
    cfg,
    layer,
    name: str,
    section: str | None,
    no: str,
    parent_chunk_id: str | None = None,
) -> list[Document]:
    """Một đơn vị nội dung -> Document đã gắn ngữ cảnh và metadata."""
    budget = layer.budget
    inherit = cfg.context.inherit
    # Ngữ cảnh cho mảnh 2 trở đi: bảng bị cắt làm ba thì mảnh sau mất câu
    # "Ý nghĩa của bảng: ...", đứng một mình chỉ còn là lưới ô.
    carried = " ".join(
        el["text"] for el in group if el.get("role") in inherit.from_roles
    ).strip()[: inherit.max_chars]

    # Phần đầu ghép vào sau khi cắt: breadcrumb (mọi mảnh) và ngữ cảnh thừa
    # hưởng (mảnh 2 trở đi). Trừ hao trước, nếu không mảnh nào cũng vượt trần
    # đúng bằng độ dài của nó.
    crumb = ""
    if cfg.context.breadcrumb.enabled:
        crumb = context_prefix(
            ir.get("title", ir["doc_id"]),
            ChunkMeta(doc_id=ir["doc_id"], section=section, table_name=name),
            separator=cfg.context.breadcrumb.separator,
            include_doc_title=cfg.context.breadcrumb.include_doc_title,
        )
    overhead = f"{crumb}\n{carried}\n"
    reserve = measure(overhead, budget=layer.budget) if crumb or carried else 0

    out: list[Document] = []
    parts = split_unit(group, layer, reserve=reserve)
    for i, (body, els) in enumerate(parts, 1):
        meta = ChunkMeta.build(
            text=body,
            doc_id=ir["doc_id"],
            section=section,
            table_name=name,
            no=no,
            part=f"{i}/{len(parts)}",
            source_path=ir.get("source_name"),
            element_ids=[el["id"] for el in els],
            line_start=els[0].get("line_start"),
            line_end=els[-1].get("line_end"),
            parent_chunk_id=parent_chunk_id,
        )
        text = body if i == 1 or not carried else f"{carried}\n{body}"
        if cfg.context.breadcrumb.enabled:
            crumb = context_prefix(
                ir.get("title", ir["doc_id"]),
                meta,
                separator=cfg.context.breadcrumb.separator,
                include_doc_title=cfg.context.breadcrumb.include_doc_title,
            )
            text = f"{crumb}\n{text}" if crumb else text
        if cfg.filter.drop_empty and not text.strip():
            continue
        # Bảo đảm cứng: cắt cụt ở ĐÂY, sau khi đã ghép breadcrumb và ngữ cảnh
        # thừa hưởng, vì đó mới là chuỗi thật sự đi vào embedder.
        if budget.on_overflow == "truncate" and measure(text, budget=budget) > budget.max:
            text = truncate(text, budget.max, budget=budget)
        out.append(Document(
            page_content=text,
            metadata=meta.with_rendered(
                text, n_tokens=measure(text, budget=layer.budget)
            ).model_dump(),
        ))
    return out


def _units(elements: list[dict], layer):
    """-> (nhóm element, tên đơn vị đã bỏ tiền tố chung)."""
    role = _unit_role(layer.split_on)
    groups = group_by_unit(elements, unit_role=role)
    raw = [
        g[0]["text"] if g[0]["modality"] == "heading" else g[0].get(role, "")
        for g in groups
    ]
    prefix = common_prefix(raw)
    names = [n[len(prefix):].strip() if prefix else n.strip() for n in raw]
    return list(zip(groups, names))


def _flat(ir: dict, cfg, layer, *, parent_chunk_id: str | None = None) -> list[Document]:
    nxt = _numbering()
    out: list[Document] = []
    for group, name in _units(ir["elements"], layer):
        section = group[0].get(SECTION_ROLE)
        out += _emit(
            group, ir=ir, cfg=cfg, layer=layer, name=name,
            section=section, no=nxt(section), parent_chunk_id=parent_chunk_id,
        )
    return out


def _full_doc_parent(ir: dict, cfg) -> Document:
    """Cả tài liệu là MỘT cha, cắt cụt ở `parent.max_length`."""
    budget = cfg.parent.budget
    elements = ir["elements"]
    text = render_all(elements, restore_labels=cfg.context.restore_labels)
    if measure(text, budget=budget) > cfg.parent.max_length:
        text = truncate(text, cfg.parent.max_length, budget=budget)

    meta = ChunkMeta.build(
        text=text,
        doc_id=ir["doc_id"],
        table_name=ir.get("title", ir["doc_id"]),
        no="0.0",
        part="1/1",
        source_path=ir.get("source_name"),
        element_ids=[el["id"] for el in elements],
        line_start=elements[0].get("line_start") if elements else None,
        line_end=elements[-1].get("line_end") if elements else None,
    )
    return Document(
        page_content=text,
        metadata=meta.with_rendered(text, n_tokens=measure(text, budget=budget)).model_dump(),
    )


def build(ir: dict, *, cfg=None) -> tuple[list[Document], list[Document]]:
    """IR -> `(chunk để embed, chunk cha để trả về)`.

    General: danh sách cha rỗng. Parent-child: con đi vào vector store, cha nằm
    ở artifact riêng và được trả về khi con khớp.
    """
    cfg = cfg or CHUNK
    if cfg.mode == "general":
        return link_neighbors(merge_underflow(_flat(ir, cfg, cfg), cfg)), []

    parent_layer = cfg.model_copy(
        update={"split_on": cfg.parent.split_on, "budget": cfg.parent.budget}
    )

    if cfg.parent.method == "full_doc":
        parent = _full_doc_parent(ir, cfg)
        pid = parent.metadata["chunk_id"]
        if cfg.child_roles:
            kept = [e for e in ir["elements"] if e.get("role") in cfg.child_roles]
            ir = {**ir, "elements": kept or ir["elements"]}
        kids = link_neighbors(merge_underflow(
            _flat(ir, cfg, cfg, parent_chunk_id=pid), cfg))
        return kids, [parent]

    nxt = _numbering()
    parents: list[Document] = []
    children: list[Document] = []
    for group, name in _units(ir["elements"], parent_layer):
        section = group[0].get(SECTION_ROLE)
        no = nxt(section)
        made = _emit(group, ir=ir, cfg=cfg, layer=parent_layer,
                     name=name, section=section, no=no)
        parents += made
        kids = [e for e in group if not cfg.child_roles or e.get("role") in cfg.child_roles]
        children += _emit(kids or group, ir=ir, cfg=cfg, layer=cfg, name=name,
                          section=section, no=no,
                          parent_chunk_id=made[0].metadata["chunk_id"] if made else None)
    return children, parents


def split(ir: dict, *, cfg=None) -> list[Document]:
    """Chỉ phần đi vào vector store. Lối tắt của `build()[0]`."""
    return build(ir, cfg=cfg)[0]


# ---- kiểm tra và ghi ------------------------------------------------------

def merge_underflow(docs: list[Document], cfg) -> list[Document]:
    """Gộp chunk dưới sàn với chunk liền kề CÙNG section.

    Gộp lùi vào chunk trước; chunk đầu tiên thì gộp tới chunk sau. Không gộp
    xuyên section vì hai section là hai chủ đề - ghép chúng lại tạo ra một chunk
    nói hai chuyện, tệ hơn một chunk ngắn.

    Chạy SAU khi đã cắt xong chứ không lồng vào thang: gộp trong lúc cắt thì
    một mảnh vừa bị cắt ra đã bị gộp lại ngay, và thang mất ý nghĩa.
    """
    budget = cfg.budget
    if budget.on_underflow != "merge" or len(docs) < 2:
        return docs

    out: list[Document] = []
    for doc in docs:
        size = _size(doc.metadata, budget.unit)
        prev = out[-1] if out else None
        fits = (
            prev is not None
            and prev.metadata["section"] == doc.metadata["section"]
            and _size(prev.metadata, budget.unit) + size <= budget.max
        )
        if size >= budget.min or not fits:
            out.append(doc)
            continue
        out[-1] = _join(prev, doc, cfg)
    return out


def _join(a: Document, b: Document, cfg) -> Document:
    """Hai chunk -> một. Metadata phải dựng lại, không chắp vá được."""
    text = f"{a.page_content}\n{b.page_content}"
    meta = ChunkMeta.build(
        text=text,
        doc_id=a.metadata["doc_id"],
        section=a.metadata["section"],
        table_name=a.metadata["table_name"],
        no=a.metadata["no"],
        part=a.metadata["part"],
        source_path=a.metadata["source_path"],
        element_ids=[*a.metadata["element_ids"], *b.metadata["element_ids"]],
        line_start=a.metadata["line_start"],
        line_end=b.metadata["line_end"],
        parent_chunk_id=a.metadata.get("parent_chunk_id"),
    )
    return Document(
        page_content=text,
        metadata=meta.with_rendered(
            text, n_tokens=measure(text, budget=cfg.budget)).model_dump(),
    )


def link_neighbors(docs: list[Document]) -> list[Document]:
    """Gắn `prev_chunk_id`/`next_chunk_id` theo thứ tự đọc trong cùng tài liệu.

    Chạy cuối cùng, sau khi gộp, vì gộp làm đổi cả số lượng lẫn `chunk_id`.
    """
    for before, doc, after in zip([None, *docs], docs, [*docs[1:], None]):
        doc.metadata["prev_chunk_id"] = before.metadata["chunk_id"] if before else None
        doc.metadata["next_chunk_id"] = after.metadata["chunk_id"] if after else None
    return docs


def _size(meta: dict, unit: str) -> int:
    return meta["n_tokens"] if unit == "token" else meta["n_chars"]


def check(chunks: list[Document], *, cfg=None, parents: list[Document] | None = None) -> list[str]:
    """Trả danh sách cảnh báo. Không tự sửa."""
    cfg = cfg or CHUNK
    budget = cfg.budget
    if not chunks:
        return [f"0 chunk - IR không có heading vai trò '{_unit_role(cfg.split_on)}'"]

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

    if cfg.mode == "parent_child":
        if orphan := sum(1 for c in chunks if not c.metadata.get("parent_chunk_id")):
            warn.append(f"{orphan} chunk con không có cha - retriever sẽ không nới được ngữ cảnh")
        # Cha bị cắt làm nhiều mảnh thì con chỉ trỏ về mảnh đầu.
        if parents and (multi := sum(1 for p in parents if p.metadata["part"] != "1/1")):
            warn.append(
                f"{multi} mảnh cha sinh ra do vượt parent.budget - "
                "con chỉ trỏ về mảnh đầu, nới rộng parent.budget.max"
            )
    return warn


def write_chunks(chunks: list[Document], *, out_dir: Path = PROCESSED_DIR, doc_id: str,
                 suffix: str = "chunks") -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    dst = out_dir / f"{doc_id}.{suffix}.jsonl"
    with dst.open("w", encoding="utf-8") as f:
        for c in chunks:
            row = {"page_content": c.page_content, "metadata": c.metadata}
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return dst


def report(chunks: list[Document], warn: list[str], *, cfg=None,
           parents: list[Document] | None = None) -> None:
    cfg = cfg or CHUNK
    if not chunks:
        print(f"     ! 0 chunk - IR không có heading vai trò '{_unit_role(cfg.split_on)}'")
        return

    unit = cfg.budget.unit
    sizes = sorted(_size(c.metadata, unit) for c in chunks)
    pieces = sum(1 for c in chunks if c.metadata["part"] != "1/1")
    print(f"     chế độ {cfg.mode} | {len(chunks)} chunk | min={sizes[0]} "
          f"p50={sizes[len(sizes) // 2]} max={sizes[-1]} {unit}")
    print(f"     có table_name: {sum(1 for c in chunks if c.metadata['table_name'])}"
          f"/{len(chunks)} | mảnh của đơn vị bị cắt: {pieces}")
    if parents:
        psize = sorted(_size(p.metadata, unit) for p in parents)
        print(f"     cha: {len(parents)} | min={psize[0]} p50={psize[len(psize) // 2]} "
              f"max={psize[-1]} {unit}")
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

    chunks, parents = build(ir)
    warn = check(chunks, parents=parents)
    dst = write_chunks(chunks, doc_id=doc_id)

    print(f"{doc_id}.linked.json\n  -> {rel(dst)}")
    if parents:
        print(f"  -> {rel(write_chunks(parents, doc_id=doc_id, suffix='parents'))}")
    report(chunks, warn, parents=parents)
    return 1 if not chunks else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

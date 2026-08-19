"""block -> nội dung theo modality. Chặng `extract`.

    uv run python -m src.branch_sql.offline.extract.block_extract mo_ta_bang_bds_new__docx

Đọc `<doc_id>.md` - artifact DUY NHẤT của chặng `parse` - rồi cắt block bằng
`blocks.split()` ngay trong chặng này.

Chọn cách xử lý theo `type` của block:

    heading    -> tên + cấp + vai trò (vai trò lấy từ profile)
    table      -> columns[] + rows[], không diễn giải ô nào mang nghĩa gì
    text       -> cắt theo nhãn rồi gán role, nhãn khai trong profile

Trung lập là yêu cầu chính: module này không chứa một chữ tiếng Việt nào trong
logic. "Mối liên kết:" là kiến thức của `config/sql.json`, không phải của code.
Bộ tài liệu khác chỉ cần đổi `extract.roles`.

Một block văn bản có thể chứa nhiều nhãn dính liền nhau:

    Mối liên kết:
    Liên kết với các bảng khác qua cột CODE
    Ghi chú:
    Thường truy xuất vào bảng này...

`parse` gom cả bốn dòng thành một block vì không có dòng trắng ngăn - đúng vai
trò của nó, vì nhận ra "Ghi chú:" là nhãn thì phải biết quy ước tài liệu. Việc
cắt ra là của chặng này.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from ...config import CFG, PROCESSED_DIR, RAW_DIR, listdir, rel
from .blocks import Block

# Hợp đồng tối thiểu của artifact extract. Quan hệ và cây cha-con thuộc link.
SCHEMA_VERSION = "1.0"

# ---- bảng -----------------------------------------------------------------

def _cell_text(inline, *, strip_emphasis: bool) -> str:
    """Nội dung một ô.

    `strip_emphasis` bật thì lấy phần text của các token con, nên `**Tên cột**`
    thành `Tên cột` mà không cần regex - và không đụng nhầm dấu `*` là nội dung
    thật. Tắt thì trả markdown gốc của ô.
    """
    if not strip_emphasis:
        return (inline.content or "").strip()
    parts = [c.content for c in (inline.children or []) if c.type in ("text", "code_inline")]
    return "".join(parts).strip() if parts else (inline.content or "").strip()


def parse_table(block: Block, *, strip_emphasis: bool = True) -> dict:
    """Block table -> columns[] + rows[].

    Đi trên token của markdown-it: `th` là ô tiêu đề, `td` là ô dữ liệu, `tr` mở
    một hàng. Không giả định ô nào mang nghĩa gì - đó là việc của chặng `link`.
    """
    from .blocks import _parser

    columns: list[str] = []
    rows: list[list[str]] = []
    row: list[str] = []
    in_head = False

    tokens = _parser().parse(block.text)
    for i, tok in enumerate(tokens):
        if tok.type == "thead_open":
            in_head = True
        elif tok.type == "thead_close":
            in_head = False
        elif tok.type == "tr_open":
            row = []
        elif tok.type == "tr_close":
            (columns.extend(row) if in_head and not columns else rows.append(row))
        elif tok.type in ("th_open", "td_open"):
            nxt = tokens[i + 1] if i + 1 < len(tokens) else None
            row.append(_cell_text(nxt, strip_emphasis=strip_emphasis) if nxt else "")

    return {
        "block_id": block.id,
        "modality": "table",
        # Markdown gốc được giữ cùng dữ liệu đã tách để không phải render ngược
        # từ columns/rows (render ngược làm mất căn lề và escape).
        "text": block.text,
        "columns": columns,
        "rows": rows,
        # Không có `records`: nó đúng bằng `zip(columns, rows)`, không có người
        # đọc, và chiếm 15% file. Cần thì dựng lại bằng một dòng.
        "n_rows": len(rows),
        "line_start": block.line_start,
        "line_end": block.line_end,
    }


# ---- văn bản --------------------------------------------------------------

def match_role(line: str, roles) -> tuple[str | None, str, str]:
    """Dòng có khớp nhãn nào không. Trả (role, nhãn đã khớp, phần còn lại).

    Trả cả nhãn vì `strip_label` cắt nó khỏi `text`: không giữ lại thì "Ý nghĩa
    của bảng:" biến mất khỏi structured element.
    """
    for cfg in roles:
        for pat in cfg.patterns:
            if m := pat.match(line.strip()):
                s = line.strip()
                return cfg.role, s[:m.end()].strip(), (s[m.end():].strip() if cfg.strip_label else s)
    return None, "", line.strip()


def parse_text(block: Block, roles) -> list[dict]:
    """Block văn bản -> một hoặc nhiều đoạn, mỗi đoạn một role.

    Cắt tại mỗi dòng khớp nhãn. Không nhãn nào khớp thì trả đúng một đoạn với
    role = null - tài liệu không theo quy ước nào vẫn đi qua được chặng này.

    Nhãn nằm ở đâu quyết định nội dung bắt đầu từ dòng nào, nên phải theo dõi
    HAI mốc chứ không một:

        "Ý nghĩa: Lưu trữ..."   nhãn dòng i, nội dung cũng dòng i
        "Mối liên kết:"         nhãn dòng i, nội dung từ dòng i+1
        "Liên kết qua cột X."

    Gộp hai ca này làm một là nguồn của lỗi lệch một dòng: khoảng dòng của đoạn
    trỏ vào dòng nhãn và bỏ sót đúng dòng chứa nội dung.
    """
    lines = block.text.splitlines()
    # (role, nhãn, dòng chứa nhãn, dòng nội dung đầu tiên, các dòng nội dung)
    segs: list[tuple[str | None, str, int, int, list[str]]] = []
    role, label, at, body_at, buf = None, "", 0, 0, []

    for i, line in enumerate(lines):
        found, lbl, rest = match_role(line, roles)
        if not found:
            buf.append(line.strip())
            continue
        if buf or role:
            segs.append((role, label, at, body_at, buf))
        role, label, at = found, lbl, i
        buf = [rest] if rest else []
        body_at = i if rest else i + 1

    segs.append((role, label, at, body_at, buf))

    out = []
    for r, lbl, at, body_at, b in segs:
        text = "\n".join(x for x in b if x).strip()
        if not text and r is None:
            continue
        # Khoảng dòng phủ cả nhãn lẫn nội dung. Nhãn đứng riêng mà nội dung nằm
        # ở block khác thì đoạn chỉ chiếm đúng dòng nhãn - `link` sẽ ghép sau.
        end = body_at + len(b) - 1 if b else at
        out.append({
            "block_id": block.id if len(segs) == 1 else f"{block.id}.{len(out) + 1}",
            "modality": "text",
            "role": r,
            "label": lbl,
            "text": text,
            "line_start": block.line_start + at,
            "line_end": block.line_start + max(end, at),
        })
    return out


# ---- điều phối ------------------------------------------------------------

def _assign_ids(out: list[dict]) -> list[dict]:
    """Đánh số ổn định theo thứ tự đọc, không dựng quan hệ giữa các element."""
    for i, el in enumerate(out, 1):
        el["id"] = f"el_{i}"
    return out


def extract(blocks: list[Block], *, cfg=None) -> list[dict]:
    """list[Block] -> list structured element độc lập.

    Chặng này chỉ đọc heading/text/table, gán role/label và giữ khoảng dòng.
    `parent_id`, tổ tiên `section`/`table`, ghép nhãn và mọi relationship đều do
    `link` tạo sau khi đã có đủ danh sách element.
    """
    cfg = cfg or CFG.extract
    out: list[dict] = []

    for b in blocks:
        if b.type == "heading":
            out.append({
                "block_id": b.id,
                "modality": "heading",
                "level": b.level,
                "role": b.role,
                "text": b.text,
                "line_start": b.line_start,
                "line_end": b.line_end,
            })
        elif b.type == "table":
            out.append(parse_table(b, strip_emphasis=cfg.strip_cell_emphasis))
        else:
            out.extend(parse_text(b, cfg.roles))

    return _assign_ids(out)


def build_ir(blocks: list[Block], *, doc_id: str, title: str | None = None,
             source_name: str | None = None, warnings: list[str] | None = None,
             cfg=None) -> dict:
    """Artifact hoàn chỉnh của chặng: envelope tài liệu + phần tử.

    Mảng trần thì mọi chặng sau phải đi tìm doc_id ở chỗ khác. `schema_version`
    để đổi hình dạng sau này còn biết mà từ chối file cũ.
    """
    from .blocks import check as check_blocks

    cfg = cfg or CFG.extract
    elements = extract(blocks, cfg=cfg)
    heading_roles = cfg.heading_roles or {
        block.level: block.role
        for block in blocks
        if block.type == "heading" and block.level and block.role
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "doc_id": doc_id,
        "title": title or doc_id,
        "source_name": source_name or doc_id,
        "warnings": [
            *(warnings or []),
            *check_blocks(blocks, roles=heading_roles),
            *check(elements),
        ],
        "elements": elements,
    }


def load_ir(doc_id: str, *, base: Path = PROCESSED_DIR) -> dict:
    src = base / f"{doc_id}.extract.json"
    if not src.exists():
        raise FileNotFoundError(
            f"không thấy {rel(src)} - chạy "
            f"`python -m src.branch_sql.offline.extract.block_extract {doc_id}` trước"
        )
    ir = json.loads(src.read_text(encoding="utf-8"))
    if ir.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(
            f"{rel(src)}: schema_version={ir.get('schema_version')}, "
            f"code cần {SCHEMA_VERSION} - chạy lại chặng extract"
        )
    return ir


def load_blocks(doc_id: str, *, base: Path = PROCESSED_DIR) -> list[Block]:
    """Đọc `<doc_id>.md` rồi cắt block.

    Không có file trung gian để đọc: block là hàm thuần của (`.md`, profile), nên
    lưu ra đĩa chỉ tạo một bản cache có thể lệch với `.md`.
    """
    from .blocks import split as split_blocks

    src = base / f"{doc_id}.md"
    if not src.exists():
        raise FileNotFoundError(
            f"không thấy {rel(src)} - chạy "
            f"`python -m src.branch_sql.offline.parse.doc_parse <file nguồn>` trước"
        )
    return split_blocks(src.read_text(encoding="utf-8"))


def source_metadata(doc_id: str, *, base: Path = RAW_DIR) -> tuple[str, str]:
    """Suy `(title, source_name)` từ file raw khi chạy riêng extract CLI.

    Pipeline chính truyền hai giá trị này trong bộ nhớ. Lệnh chạy từng chặng
    không có metadata sidecar, nên đối chiếu `doc_id` với tên file raw.
    """
    from ..parse.doc_parse import doc_id_of

    matches = (
        [path for path in base.iterdir() if path.is_file() and doc_id_of(path) == doc_id]
        if base.is_dir()
        else []
    )
    if len(matches) == 1:
        return matches[0].stem, matches[0].name
    return doc_id, doc_id


def write(ir: dict, *, out_dir: Path = PROCESSED_DIR) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    dst = out_dir / f"{ir['doc_id']}.extract.json"
    dst.write_text(json.dumps(ir, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return dst


def check(elements: list[dict]) -> list[str]:
    """Trả danh sách cảnh báo cấu trúc của extract."""
    warn: list[str] = []
    if not elements:
        return ["0 phần tử - không cắt được block nào từ .md"]

    if n := sum(1 for e in elements if e["modality"] == "text" and not e.get("role")):
        warn.append(f"{n} đoạn không khớp nhãn nào trong extract.roles")
    if n := sum(1 for e in elements if e["modality"] == "table" and not e["columns"]):
        warn.append(f"{n} bảng không có dòng tiêu đề - hàng đầu bị hiểu nhầm là dữ liệu")
    return warn


def report(elements: list[dict], warnings: list[str] | None = None) -> None:
    from collections import Counter

    mods = Counter(e["modality"] for e in elements)
    print(f"     {len(elements)} phần tử | " + " ".join(f"{k}={v}" for k, v in sorted(mods.items())))

    roles = Counter(e.get("role") for e in elements if e["modality"] == "text")
    for r, n in sorted(roles.items(), key=lambda kv: (kv[0] is None, kv[0] or "")):
        print(f"       role {str(r):<16} {n}")

    tables = [e for e in elements if e["modality"] == "table"]
    if tables:
        print(f"     bảng: {len(tables)} | tổng {sum(t['n_rows'] for t in tables)} dòng")

    # Nhãn chưa có nội dung là ĐẦU VÀO của `link.caption_of`, không phải lỗi.
    # In ra để thấy hai định dạng có tới `link` cùng trạng thái hay không.
    if n := sum(1 for e in elements if e["modality"] == "text" and e.get("label") and not e["text"]):
        print(f"     nhãn chờ link.caption_of ghép: {n}")

    for w in warnings if warnings is not None else check(elements):
        print(f"     ! {w}")


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        print(f"file có sẵn trong {rel(PROCESSED_DIR)}:")
        for n in listdir(PROCESSED_DIR, "*.md"):
            print(f"  - {n.removesuffix('.md')}")
        return 1

    doc_id = argv[0].removesuffix(".md")
    try:
        blocks = load_blocks(doc_id)
    except FileNotFoundError as e:
        print(e, file=sys.stderr)
        return 1

    if not CFG.extract.roles:
        print("! extract.roles rỗng - bảng vẫn tách được, nhưng không đoạn nào có role")

    title, source_name = source_metadata(doc_id)
    ir = build_ir(
        blocks,
        doc_id=doc_id,
        title=title,
        source_name=source_name,
    )
    dst = write(ir)
    print(f"{doc_id}.md\n  -> {rel(dst)}")
    report(ir["elements"], ir["warnings"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

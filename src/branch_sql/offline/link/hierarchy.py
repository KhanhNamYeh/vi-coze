"""Structured elements -> cây cha-con. Chặng `link`.

    uv run python -m src.branch_sql.offline.link.hierarchy mo_ta_bang_bds_new__docx

Đọc `<doc_id>.extract.json`, ghi `<doc_id>.linked.json`. `extract` cho ra element
độc lập theo thứ tự đọc; chặng này gắn `parent_id`, gắn tên tổ tiên theo vai trò
heading, và ghép nhãn đứng riêng với nội dung ngay sau nó. Chỉ có thế — quan hệ
nghiệp vụ giữa các bảng là việc của chặng `graph`.

Không có khoá cấu hình: vai trò tổ tiên lấy thẳng từ `role` của heading trong tài
liệu, nên hồ sơ đặt tên là `table`, `entity` hay `chapter` đều chạy như nhau.
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

from ...config import PROCESSED_DIR, listdir, rel
from ..extract.block_extract import SCHEMA_VERSION, load_ir


def attach_hierarchy(elements: list[dict]) -> list[dict]:
    """Dựng cây heading, gắn `parent_id` và tên tổ tiên lên bản sao của element."""
    out: list[dict] = []
    stack: list[tuple[int, dict]] = []

    for source in elements:
        el = dict(source)
        is_heading = el.get("modality") == "heading" and el.get("level")

        if is_heading:
            while stack and stack[-1][0] >= el["level"]:
                stack.pop()

        el["parent_id"] = stack[-1][1]["id"] if stack else None
        for _, heading in stack:
            if heading.get("role"):
                el[heading["role"]] = heading["text"]

        out.append(el)
        if is_heading:
            stack.append((el["level"], el))

    return out


def merge_standalone_labels(elements: list[dict]) -> list[dict]:
    """Ghép nhãn text rỗng với block text không nhãn đứng ngay sau nó.

    Nhãn đứng trước một BẢNG không bị nuốt: "Chi tiết các cột:" là câu dẫn, dính
    vào hàng tiêu đề thì hỏng cú pháp markdown. Nó ở lại thành element riêng và
    vẫn vào chunk như một dòng - đúng thứ RAG cần.
    """
    out: list[dict] = []
    i = 0
    while i < len(elements):
        el = dict(elements[i])
        nxt = elements[i + 1] if i + 1 < len(elements) else None
        if (
            el.get("modality") == "text"
            and el.get("label")
            and not el.get("text")
            and nxt is not None
            and nxt.get("modality") == "text"
            and not nxt.get("label")
            and not nxt.get("role")
            and nxt.get("parent_id") == el.get("parent_id")
        ):
            el["text"] = nxt["text"]
            el["line_end"] = nxt["line_end"]
            i += 1
        out.append(el)
        i += 1
    return out


def link(ir: dict) -> dict:
    """Extract envelope -> linked envelope, không sửa object đầu vào."""
    elements = merge_standalone_labels(attach_hierarchy(ir["elements"]))
    linked = {**ir, "schema_version": SCHEMA_VERSION, "elements": elements}
    linked["warnings"] = [*ir.get("warnings", []), *check(linked)]
    return linked


def check(ir: dict) -> list[str]:
    """Trả danh sách cảnh báo. Không tự sửa."""
    elements = ir["elements"]
    if not elements:
        return ["0 phần tử - extract không tạo được element nào"]

    warn: list[str] = []
    # Mỗi cha chứa những loại element nào. Một lượt quét, dùng cho cả hai luật dưới.
    kinds: dict[str | None, set[str]] = defaultdict(set)
    for el in elements:
        kinds[el.get("parent_id")].add(el["modality"])

    if n := sum(
        1 for e in elements if e.get("modality") != "heading" and not e.get("parent_id")
    ):
        warn.append(f"{n} phần tử nằm ngoài mọi heading")

    # Nhãn rỗng là câu dẫn vào một object CÙNG CHA, không nhất thiết đứng kề: bản
    # pdf xếp 17/18 nhãn cách bảng bởi text khác. Chỉ hỏng khi cùng cha không có
    # object nào để dẫn tới.
    if orphan := [
        e["id"]
        for e in elements
        if e.get("label") and not e.get("text") and kinds[e.get("parent_id")] <= {"text", "heading"}
    ]:
        warn.append(
            f"{len(orphan)} nhãn rỗng không tìm được nội dung - {', '.join(orphan[:5])}"
        )

    # Heading cấp sâu nhất là đơn vị nội dung của tài liệu. Chỉ soi khi tài liệu
    # thật sự có bảng - tài liệu toàn văn xuôi thì luật này vô nghĩa.
    levels = [e["level"] for e in elements if e.get("modality") == "heading" and e.get("level")]
    if levels and any(e["modality"] == "table" for e in elements):
        deepest = max(levels)
        if n := sum(
            1
            for e in elements
            if e.get("level") == deepest
            and e.get("modality") == "heading"
            and "table" not in kinds[e["id"]]
        ):
            warn.append(f"{n} heading cấp {deepest} không có bảng nào bên dưới")

    return warn


def load_linked(doc_id: str, *, base: Path = PROCESSED_DIR) -> dict:
    """Artifact của chặng này. `chunk` cần ancestor nên phải đọc file NÀY, không
    đọc `.extract.json` - element ở đó chưa có `section`/`table`."""
    src = base / f"{doc_id}.linked.json"
    if not src.exists():
        raise FileNotFoundError(
            f"không thấy {rel(src)} - chạy "
            f"`python -m src.branch_sql.offline.link.hierarchy {doc_id}` trước"
        )
    ir = json.loads(src.read_text(encoding="utf-8"))
    if ir.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(
            f"{rel(src)}: schema_version={ir.get('schema_version')}, "
            f"code cần {SCHEMA_VERSION} - chạy lại chặng link"
        )
    return ir


def write(ir: dict, *, out_dir: Path = PROCESSED_DIR) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    dst = out_dir / f"{ir['doc_id']}.linked.json"
    dst.write_text(json.dumps(ir, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return dst


def report(ir: dict, warnings: list[str] | None = None) -> None:
    elements = ir["elements"]
    roots = sum(1 for e in elements if not e.get("parent_id"))
    # Nhãn còn rỗng là nhãn dẫn vào bảng - số đo, không phải lỗi.
    labels = sum(1 for e in elements if e.get("label") and not e.get("text"))

    print(f"     {len(elements)} phần tử | {roots} gốc | {len(elements) - roots} có cha")
    if labels:
        print(f"     nhãn dẫn vào bảng, đứng riêng: {labels}")
    for warning in warnings if warnings is not None else check(ir):
        print(f"     ! {warning}")


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        print(f"file có sẵn trong {rel(PROCESSED_DIR)}:")
        for name in listdir(PROCESSED_DIR, "*.extract.json"):
            print(f"  - {name.removesuffix('.extract.json')}")
        return 1

    doc_id = argv[0].removesuffix(".extract.json").removesuffix(".md")
    try:
        ir = link(load_ir(doc_id))
    except (FileNotFoundError, ValueError) as error:
        print(error, file=sys.stderr)
        return 1

    dst = write(ir)
    print(f"{doc_id}.extract.json\n  -> {rel(dst)}")
    report(ir, ir["warnings"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

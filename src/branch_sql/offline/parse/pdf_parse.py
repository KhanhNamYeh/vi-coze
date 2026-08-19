"""pdf -> markdown có heading. Một trong hai loader của chặng `parse`.

Dùng `docling` chứ không dùng `markitdown`: markitdown đọc PDF qua pdfminer và
chỉ trả về text thuần, các ô của bảng dính liền nhau và ngắt dòng giữa chừng nên
không còn ranh giới cột. Với bộ tài liệu này, mất bảng là mất đúng phần dữ liệu
cần dùng. Docling chạy mô hình nhận diện layout nên dựng lại được bảng.

Đọc thẳng `DoclingDocument`, KHÔNG đi qua `export_to_markdown()`. Bản xuất
markdown bẹp mọi thứ xuống text: mục lục thành bảng ba cột, đoạn văn dính dấu
`- `/`- -`/`●`, dấu `_` bị escape, dải gạch ngăn trang thành heading gạch dưới.
Dựng ngược từ đó cần bảy luật regex vá từng triệu chứng. Object model thì có sẵn
nhãn loại, số thứ tự, số trang và lưới ô của bảng, nên chỉ còn hai luật — và cả
hai đều phát biểu về quy ước của tài liệu, không phải vá lỗi thư viện:

    1. Tài liệu đánh số tiêu đề, nên SỐ quyết định cấp bậc: "1." là nhóm,
       "1.1." là bảng. Docling gán mọi tiêu đề level=1 và đọc nhầm ba tên bảng
       thành gạch đầu dòng, nhưng số thứ tự vẫn còn nguyên ở `marker`.
       Hệ quả: thứ gì trước tiêu đề đánh số đầu tiên là bìa và mục lục, bỏ.
    2. Hai bảng liền kề nhau là một bảng bị ngắt trang, nối lại.

Cái giá của docling: lần chạy đầu phải tải mô hình, mỗi lần convert tốn ~75 giây
cho 20 trang, so với dưới một giây của markitdown. Vì vậy nó nằm ở extra `pdf` và
chỉ được import khi thật sự gặp file .pdf:

    uv sync --extra pdf
    uv run --extra pdf python -m src.branch_sql.offline "tài liệu.pdf"

Sau hai luật trên, bản .pdf ngang bản .docx: 18/18 bảng, 194 dòng dữ liệu, khớp
từng bảng một. Khác biệt còn lại chỉ là thời gian.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

# Tiêu đề đánh số của tài liệu: "1. Danh mục" hoặc "1.1. Bảng X".
NUMBERED = re.compile(r"^(?P<no>\d+(?:\.\d+)*)\.?\s+(?P<name>.+)$")
# Chỉ nhận marker từ HAI cấp trở lên. Gạch đầu dòng trong thân bài cũng được
# docling đánh số, nhưng luôn một cấp ("5.", "9."), nên hai cấp mới đủ đặc trưng.
MULTILEVEL = re.compile(r"^\d+(?:\.\d+)+$")
# Docling thường cắt ký tự gạch đầu dòng khỏi `text`, nhưng không phải lúc nào
# cũng cắt. Sót lại thì nhãn "Mối liên kết:" không còn nằm đầu dòng và `extract`
# mất role.
LEADING_BULLET = re.compile(r"(?m)^[●○•▪]\s*|^-(?=\S)")


def _label(item) -> str:
    lb = getattr(item, "label", "")
    return str(getattr(lb, "value", lb))


def heading_of(item) -> tuple[int, str] | None:
    """(độ sâu, tên) nếu item là tiêu đề đánh số, ngược lại None.

    Hai nguồn số, cùng một luật: tiêu đề docling nhận đúng thì số nằm trong
    `text`; tiêu đề bị đọc nhầm thành gạch đầu dòng thì số nằm ở `marker`.
    """
    if _label(item) == "section_header":
        if m := NUMBERED.match((item.text or "").strip()):
            return m["no"].count(".") + 1, m["name"].strip()
        return None

    marker = (getattr(item, "marker", "") or "").strip().rstrip(".")
    if MULTILEVEL.fullmatch(marker):
        return marker.count(".") + 1, (item.text or "").strip()
    return None


def table_markdown(run: list, doc) -> str:
    """Một dãy bảng liền kề -> một bảng markdown.

    Bảng vắt qua ranh giới trang bị docling cắt làm đôi, nửa sau không có dòng
    tiêu đề. Để rời thì `extract` lấy nhầm dòng dữ liệu đầu tiên làm tên cột.
    """
    lines = run[0].export_to_markdown(doc).splitlines()
    for cont in run[1:]:
        rest = cont.export_to_markdown(doc).splitlines()
        # rest[0] mang danh tiêu đề nhưng thật ra là dữ liệu; rest[1] là dòng
        # ngăn cách, bỏ đi vì bảng đã có một dòng ngăn cách rồi.
        lines += rest[:1] + rest[2:]
    return "\n".join(lines)


def render(doc) -> str:
    """DoclingDocument -> markdown có `#` nhóm / `##` bảng."""
    out: list[str] = []
    items = [it for it, _ in doc.iterate_items()]
    i = 0
    started = False  # mọi thứ trước tiêu đề đánh số đầu tiên là trang bìa / mục lục

    while i < len(items):
        item = items[i]
        label = _label(item)

        if not started and not heading_of(item):
            i += 1
            continue
        started = True

        if label == "table":
            run = []
            while i < len(items) and _label(items[i]) == "table":
                run.append(items[i])
                i += 1
            out += ["", table_markdown(run, doc), ""]
            continue

        if h := heading_of(item):
            depth, name = h
            out += ["", f"{'#' * min(depth, 6)} {name}", ""]
        elif text := LEADING_BULLET.sub("", (item.text or "").strip()).strip():
            out.append(text)
        i += 1

    return "\n".join(out)


def _converter():
    # Windows: torch.compile/triton hỏng trong docling, phải tắt TRƯỚC khi import
    os.environ.setdefault("TORCH_COMPILE_DISABLE", "1")
    os.environ.setdefault("TORCHDYNAMO_DISABLE", "1")

    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions
    from docling.document_converter import DocumentConverter, PdfFormatOption

    opts = PdfPipelineOptions()
    opts.do_ocr = False              # tài liệu có text layer sẵn
    opts.do_table_structure = True   # lý do duy nhất chọn docling
    return DocumentConverter(format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=opts)})


def to_markdown(src: Path) -> str:
    """.pdf -> markdown đã dựng cấu trúc, chưa làm sạch."""
    try:
        conv = _converter()
    except ImportError as e:
        raise ImportError(f"đọc .pdf cần docling: uv sync --extra pdf\n  ({e})") from e
    return render(conv.convert(str(src)).document)

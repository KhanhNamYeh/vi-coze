"""
PDF Loader for RAG

Input:
    PDF document

Output:
    JSONL
    Each page = one JSON record

Compatible with:
    Docling 2.119.0
"""


import os

# Disable torch compile / triton issue on Windows
os.environ["TORCH_COMPILE_DISABLE"] = "1"
os.environ["TORCHDYNAMO_DISABLE"] = "1"


import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path


from docling.document_converter import (
    DocumentConverter,
    PdfFormatOption
)

from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions



if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(
        encoding="utf-8"
    )



# ============================================================
# TEXT CLEANING
# ============================================================

def clean_text(text: str) -> str:
    """
    Chuẩn hóa text tiếng Việt
    """

    if not text:
        return ""


    text = unicodedata.normalize(
        "NFC",
        text
    )


    # remove invisible chars
    text = re.sub(
        r"[\u200b\u200c\u200d\u2060\ufeff]",
        "",
        text
    )


    # normalize spaces
    text = re.sub(
        r"[ \t]+",
        " ",
        text
    )


    # normalize empty lines
    text = re.sub(
        r"\n{3,}",
        "\n\n",
        text
    )


    return text.strip()



# ============================================================
# DOCLING CONFIG
# ============================================================

def create_converter():

    pipeline_options = PdfPipelineOptions()


    # PDF có text layer
    pipeline_options.do_ocr = False


    # giữ cấu trúc bảng
    pipeline_options.do_table_structure = True



    converter = DocumentConverter(
        format_options={
            InputFormat.PDF:
                PdfFormatOption(
                    pipeline_options=pipeline_options
                )
        }
    )


    return converter



# ============================================================
# EXTRACT PAGES - SIMPLIFIED APPROACH
# ============================================================

def extract_pages(document):

    """
    Extract text từ PDF

    Docling 2.119 - Approach:
    1. Get full text using export_to_markdown/text
    2. Split into pages based on page count
    """

    pages = []

    print(
        "Detected pages:",
        len(document.pages)
    )

    # Get full document text using markdown export
    try:
        # This is the most reliable method in Docling 2.x
        full_text = document.export_to_markdown()

        if not full_text or len(full_text.strip()) == 0:
            print(
                "! export_to_markdown() returned empty"
            )
            raise ValueError(
                "No markdown content"
            )

        print(
            f"✓ Got {len(full_text)} chars from export_to_markdown()"
        )

        # Split proportionally by page
        num_pages = len(document.pages)
        
        if num_pages <= 0:
            print("! No pages found")
            return pages

        # More intelligent splitting
        lines = full_text.split("\n")
        lines_per_page = max(
            1,
            len(lines) // num_pages
        )

        page_lines = []
        current_page = []

        for i, line in enumerate(lines):

            current_page.append(line)

            if (
                (i + 1) % lines_per_page == 0
                or i == len(lines) - 1
            ):

                page_text = "\n".join(current_page)
                page_text = clean_text(page_text)

                if page_text:
                    pages.append(page_text)

                current_page = []

        # Ensure we have content
        if len(pages) == 0 and full_text.strip():
            # Fallback: put all in one page if nothing extracted
            pages.append(
                clean_text(full_text)
            )

        print(
            f"✓ Extracted {len(pages)} pages"
        )
        return pages

    except Exception as e:
        print(
            f"✗ export_to_markdown failed: {e}"
        )

    # FALLBACK: Try export_to_text
    try:
        if hasattr(document, "export_to_text"):
            full_text = document.export_to_text()

            if full_text and len(full_text.strip()) > 0:
                print(
                    f"✓ Got {len(full_text)} chars from export_to_text()"
                )

                # Split same way
                lines = full_text.split("\n")
                lines_per_page = max(
                    1,
                    len(lines) // len(document.pages)
                )

                current_page = []

                for i, line in enumerate(lines):
                    current_page.append(line)

                    if (
                        (i + 1) % lines_per_page == 0
                        or i == len(lines) - 1
                    ):
                        page_text = "\n".join(current_page)
                        page_text = clean_text(page_text)

                        if page_text:
                            pages.append(page_text)

                        current_page = []

                print(
                    f"✓ Extracted {len(pages)} pages from export_to_text()"
                )
                return pages

    except Exception as e:
        print(
            f"✗ export_to_text failed: {e}"
        )

    # LAST RESORT: Iterate pages directly
    print(
        "Using fallback: iterate pages directly"
    )

    for page_no, page in enumerate(
        document.pages.values(),
        start=1
    ):

        page_text = ""

        # Try any method available
        if hasattr(page, "export_to_markdown"):
            try:
                page_text = page.export_to_markdown()
            except:
                pass

        if not page_text and hasattr(
            page, "text"
        ):
            page_text = page.text

        if not page_text and hasattr(
            page, "elements"
        ):
            for elem in page.elements:
                if hasattr(elem, "text"):
                    page_text += elem.text + "\n"

        page_text = clean_text(page_text)
        pages.append(page_text)

    return pages




# ============================================================
# PDF TO JSONL
# ============================================================

def convert_pdf(
    pdf_path: Path,
    output_path: Path
):

    print(
        f"Processing: {pdf_path}"
    )


    converter = create_converter()



    result = converter.convert(
        str(pdf_path)
    )


    document = result.document



    pages = extract_pages(
        document
    )



    output_path.parent.mkdir(
        parents=True,
        exist_ok=True
    )



    count = 0



    with output_path.open(
        "w",
        encoding="utf-8"
    ) as f:



        for page_no, page_text in enumerate(
            pages,
            start=1
        ):


            if not page_text:
                continue



            record = {


                "id":
                    f"{pdf_path.stem}_page_{page_no}",



                "content":
                    page_text,



                "metadata": {


                    "source":
                        pdf_path.name,


                    "page":
                        page_no,


                    "title":
                        pdf_path.stem,


                    "file_type":
                        "pdf"

                }

            }



            f.write(
                json.dumps(
                    record,
                    ensure_ascii=False
                )
                + "\n"
            )


            count += 1



    print("=" * 60)
    print("DONE")
    print(
        f"Documents exported: {count}"
    )
    print(
        f"Output: {output_path}"
    )
    print("=" * 60)




# ============================================================
# CLI
# ============================================================

def main():

    parser = argparse.ArgumentParser(
        description="Convert PDF into JSONL for RAG"
    )


    parser.add_argument(
        "--input",
        required=True,
        type=Path
    )


    parser.add_argument(
        "--output",
        default=Path(
            "data/processed/pdf/pdf_extract.jsonl"
        ),
        type=Path
    )


    args = parser.parse_args()



    if not args.input.exists():

        raise FileNotFoundError(
            args.input
        )



    convert_pdf(
        args.input,
        args.output
    )




if __name__ == "__main__":
    main()
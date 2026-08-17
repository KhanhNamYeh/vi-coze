"""
Optimized RAG Chunker

Input:
    pdf_extract.jsonl

Output:
    chunked.jsonl

Designed for:
    Vietnamese academic PDF RAG
"""

import argparse
import json
import sys
from pathlib import Path
from dataclasses import dataclass
from typing import Any, Literal


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(
        encoding="utf-8"
    )


from langchain_text_splitters import (
    RecursiveCharacterTextSplitter,
    TokenTextSplitter
)

import tiktoken



# ============================================================
# CONFIG
# ============================================================

@dataclass
class ChunkConfig:

    strategy: Literal[
        "size",
        "token",
        "semantic"
    ] = "token"

    chunk_size: int = 1000

    chunk_overlap: int = 150

    target_tokens: int = 600

    token_overlap: int = 100

    min_size: int = 150

    max_size: int = 2500

    add_header: bool = True



# ============================================================
# TOKEN COUNTER
# ============================================================

class TokenCounter:

    def __init__(
        self,
        model="cl100k_base"
    ):

        try:
            self.encoder = tiktoken.get_encoding(
                model
            )

        except Exception:

            self.encoder = None



    def count(
        self,
        text: str
    ) -> int:

        if self.encoder:

            return len(
                self.encoder.encode(text)
            )

        return max(
            1,
            len(text) // 4
        )



# ============================================================
# SPLITTER
# ============================================================

def create_splitter(
    config: ChunkConfig
):


    separators = [
        "\n\n",
        "\n",
        ". ",
        "! ",
        "? ",
        " ",
        ""
    ]


    if config.strategy == "token":

        return TokenTextSplitter(

            encoding_name="cl100k_base",

            chunk_size=config.target_tokens,

            chunk_overlap=config.token_overlap

        )


    if config.strategy == "semantic":

        return RecursiveCharacterTextSplitter(

            chunk_size=config.chunk_size,

            chunk_overlap=config.chunk_overlap,

            separators=separators

        )


    return RecursiveCharacterTextSplitter(

        chunk_size=config.chunk_size,

        chunk_overlap=config.chunk_overlap,

        separators=separators

    )



# ============================================================
# HEADER
# ============================================================

def create_context_header(
    metadata: dict[str, Any]
):

    title = metadata.get(
        "title",
        ""
    )

    source = metadata.get(
        "source",
        ""
    )

    page = metadata.get(
        "page",
        ""
    )


    return (
        "[DOCUMENT CONTEXT]\n"
        f"Title: {title}\n"
        f"Source: {source}\n"
        f"Page: {page}\n"
        "---\n"
    )



# ============================================================
# STATS
# ============================================================

@dataclass
class ChunkStats:

    total_chunks: int = 0

    total_chars: int = 0

    total_tokens: int = 0

    min_tokens: int = 999999

    max_tokens: int = 0



    def add(
        self,
        text,
        counter
    ):

        tokens = counter.count(
            text
        )

        self.total_chunks += 1

        self.total_chars += len(
            text
        )

        self.total_tokens += tokens

        self.min_tokens = min(
            self.min_tokens,
            tokens
        )

        self.max_tokens = max(
            self.max_tokens,
            tokens
        )



    def report(self):

        avg = 0

        if self.total_chunks:

            avg = (
                self.total_tokens
                /
                self.total_chunks
            )


        print("\n📊 CHUNK STATISTICS")
        print("=" * 60)

        print(
            f"Total chunks: {self.total_chunks}"
        )

        print(
            f"Total chars: {self.total_chars}"
        )

        print(
            f"Total tokens: {self.total_tokens}"
        )

        print(
            f"Token min: {self.min_tokens}"
        )

        print(
            f"Token max: {self.max_tokens}"
        )

        print(
            f"Token avg: {avg:.0f}"
        )

        print("=" * 60)



# ============================================================
# CHUNK DOCUMENT
# ============================================================

def chunk_document(
    doc_json,
    splitter,
    counter,
    config,
    stats
):

    content = (

        doc_json.get("content")

        or doc_json.get("text")

        or ""

    )


    if not content.strip():

        return []



    metadata = doc_json.get(
        "metadata",
        {}
    )


    doc_id = doc_json.get(
        "id",
        ""
    )


    texts = splitter.split_text(
        content
    )


    results = []


    total = len(
        texts
    )


    for index, text in enumerate(
        texts,
        start=1
    ):


        if len(text.strip()) < config.min_size:

            continue



        if config.add_header:

            chunk_content = (

                create_context_header(
                    metadata
                )

                +

                f"[Chunk {index}/{total}]\n"

                +

                text

            )

        else:

            chunk_content = text



        stats.add(
            chunk_content,
            counter
        )


        results.append({

            "chunk_id":
                f"{doc_id}_chunk_{index}",


            "doc_id":
                doc_id,


            "chunk_index":
                index,


            "chunk_content":
                chunk_content,


            "metrics":

                {
                    "char_count":
                        len(chunk_content),

                    "token_count":
                        counter.count(
                            chunk_content
                        )
                },


            "metadata":

                {
                    **metadata,

                    "chunk_strategy":
                        config.strategy,

                    "total_chunks":
                        total
                }

        })


    return results



# ============================================================
# PROCESS
# ============================================================

def process_chunking(
    input_path,
    output_path,
    config
):


    counter = TokenCounter()

    stats = ChunkStats()


    splitter = create_splitter(
        config
    )


    total_docs = 0

    total_chunks = 0



    with (

        open(
            input_path,
            "r",
            encoding="utf-8"
        ) as infile,

        open(
            output_path,
            "w",
            encoding="utf-8"
        ) as outfile

    ):


        for line in infile:


            if not line.strip():

                continue


            doc = json.loads(
                line
            )


            total_docs += 1


            chunks = chunk_document(

                doc,

                splitter,

                counter,

                config,

                stats

            )


            for chunk in chunks:

                outfile.write(

                    json.dumps(
                        chunk,
                        ensure_ascii=False
                    )

                    +

                    "\n"

                )


                total_chunks += 1



    print("\n✅ CHUNKING COMPLETE")

    print(
        f"Documents: {total_docs}"
    )

    print(
        f"Chunks: {total_chunks}"
    )

    print(
        f"Output: {output_path}"
    )


    stats.report()



# ============================================================
# CLI
# ============================================================

def main():


    parser = argparse.ArgumentParser(
        description="Optimized RAG Chunker"
    )


    parser.add_argument(

        "--input",

        type=Path,

        default=Path(
            "data/processed/pdf/pdf_extract.jsonl"
        )

    )


    parser.add_argument(

        "--output",

        type=Path,

        default=Path(
            "data/processed/pdf/chunked.jsonl"
        )

    )


    parser.add_argument(

        "--strategy",

        choices=[
            "size",
            "token",
            "semantic"
        ],

        default="token"

    )


    parser.add_argument(

        "--chunk-size",

        type=int,

        default=1000

    )


    parser.add_argument(

        "--overlap",

        type=int,

        default=150

    )


    parser.add_argument(

        "--target-tokens",

        type=int,

        default=600

    )


    parser.add_argument(

        "--token-overlap",

        type=int,

        default=100

    )


    args = parser.parse_args()



    config = ChunkConfig(

        strategy=args.strategy,

        chunk_size=args.chunk_size,

        chunk_overlap=args.overlap,

        target_tokens=args.target_tokens,

        token_overlap=args.token_overlap

    )


    process_chunking(

        args.input,

        args.output,

        config

    )



if __name__ == "__main__":
    main()
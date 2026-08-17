# vi-coze

Pipeline RAG tiếng Việt. Hai nhánh tài liệu, chung một bộ chặng xử lý.

## Cấu trúc

Chặng xử lý chia theo **chức năng**, nhánh chia theo **bộ tài liệu**. Mỗi nhánh
chỉ có ba file: `offline.py` nạp tri thức, `online.py` truy vấn, `config.py` giữ
đường dẫn và tham số. Thứ tự nối các chặng nằm trong `offline.py`, không nằm
trong `src/offline/`.

```
src/
├── schemas.py                  hợp đồng chunk chung cho mọi nhánh
│
├── offline/                    CÁC CHẶNG — dùng chung
│   ├── parse/                  tài liệu gốc -> văn bản có tọa độ
│   │   ├── docx_parse.py           .docx -> markdown        [sql]
│   │   ├── pdf_parse.py            .pdf  -> block+page      [rag_docs]
│   │   ├── image_extractor.py      tách hình khỏi pdf
│   │   └── image_captioner.py      sinh caption cho hình
│   ├── extract/                văn bản -> cấu trúc tường minh
│   │   └── merge_documents.py      gộp text + caption       [rag_docs]
│   ├── link/                   cấu trúc -> quan hệ
│   │   └── knowledge_graph.py      graph node-link          [sql]
│   ├── chunk/                  cấu trúc -> chunk
│   │   ├── table_chunker.py        1 bảng = 1 chunk         [sql]
│   │   └── text_chunker.py         cắt theo token           [rag_docs]
│   ├── embed/                  chunk -> vector
│   │   ├── dense.py                dùng chung index + query
│   │   ├── sparse.py               BM25
│   │   └── kg_embedder.py          embed triple (prototype)
│   ├── index/                  vector -> store
│   │   ├── qdrant_store.py         dense + sparse           [sql]
│   │   └── chroma_store.py         dense                    [rag_docs]
│   └── verify/                 đối soát ngược về tài liệu gốc
│       └── inspect_chunks.py       thống kê phân bố chunk
│
├── online/                     TRUY HỒI — dùng chung
│   ├── qdrant_retriever.py         hybrid dense + BM25      [sql]
│   ├── rerank.py                   cross-encoder tiếng Việt [sql]
│   ├── chroma_retriever.py         similarity search        [rag_docs]
│   ├── bge_reranker.py             cross-encoder bge        [rag_docs]
│   └── kg_retriever.py             truy hồi trên graph (prototype)
│
├── branch_sql/                 NHÁNH tài liệu mô tả schema CSDL
│   ├── config.py
│   ├── offline.py                  parse -> chunk -> [link] -> embed -> index
│   └── online.py                   query -> hybrid -> RRF -> rerank
│
└── branch_rag_docs/            NHÁNH tài liệu PDF
    ├── config.py
    ├── offline.py                  parse -> [extract] -> chunk -> embed + index
    └── online.py                   query -> similarity -> rerank
```

`extract/` và `verify/` mới có chỗ đứng chứ chưa có nội dung cho nhánh SQL —
đó là hai chặng còn thiếu để chứng minh tri thức không mất mát. Xem docstring
trong `__init__.py` của từng chặng để biết cần bổ sung gì.

## data/

Chia theo vai trò trước, rồi mới theo bộ tài liệu:

```
data/
├── raw/<kb>/         đầu vào người dùng cung cấp — pipeline không ghi vào
├── processed/<kb>/   artifact sinh ra, xoá đi chạy lại được
├── index/            vector store trên đĩa (chroma/, kb_index.npz)
└── eval/<kb>/        bộ gold để đo độ chính xác
```

`<kb>` là `sql` và `rag_docs`, khớp tên với hai branch.

## Chạy

```bash
uv sync                              # nhánh sql
docker compose up -d                 # Qdrant

uv run python -m src.branch_sql.offline "Mô tả bảng BĐS (NEW).docx"
uv run python -m src.branch_sql.online  "Bảng nào lưu doanh thu tài khoản chính?"
```

```bash
uv sync --extra rag_docs             # nhánh pdf
uv run python -m src.branch_rag_docs.offline "[Reading]-RAG-System.pdf"
uv run python -m src.branch_rag_docs.online  "RAG gồm những thành phần nào?"
```

Từng chặng vẫn chạy riêng được để tune:

```bash
uv run python -m src.offline.parse.docx_parse    "Mô tả bảng BĐS (NEW).docx"
uv run python -m src.offline.chunk.table_chunker mo_ta_bang_bds_new.md
uv run python -m src.offline.index.qdrant_store  mo_ta_bang_bds_new.chunks.jsonl
uv run python -m src.online.qdrant_retriever     "bảng nào lưu doanh thu TKC"
```

Chi tiết: [docs/README-sql-pipeline.md](docs/README-sql-pipeline.md) ·
[docs/README-pdf-pipeline.md](docs/README-pdf-pipeline.md) ·
báo cáo kỹ thuật [report.md](report.md).

## Hai nhánh chưa hợp nhất ở đâu

Chung thư mục chặng không có nghĩa là chung cách làm. Ba khác biệt còn lại:

| | `branch_sql` | `branch_rag_docs` |
|---|---|---|
| Dense model | `AITeamVN/Vietnamese_Embedding` (1024d) | `BAAI/bge-m3` |
| Sparse | fastembed `Qdrant/bm25` | không có, nên không hybrid |
| Store | Qdrant | Chroma |

Vector hai bên **không so sánh được với nhau**, nên chưa trộn kết quả được. Đây
là việc cần làm trước khi nói tới truy hồi xuyên hai bộ tài liệu.

## Thư viện

Khai báo tập trung ở [pyproject.toml](pyproject.toml). Mặc định `uv sync` chỉ cài
phần cần cho nhánh SQL; hai phần nặng tách thành extra `kg` và `rag_docs`.

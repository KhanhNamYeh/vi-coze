# vi-coze

Pipeline RAG tiếng Việt. Hai nhánh tài liệu, chung một bộ chặng xử lý.

## Cấu trúc

Chặng xử lý chia theo **chức năng**, nhánh chia theo **bộ tài liệu**. Mỗi nhánh
chỉ có ba file: `offline.py` nạp tri thức, `online.py` truy vấn, `config.py` nạp
profile JSON. Thứ tự nối các chặng nằm trong `offline.py`, không nằm trong
`src/offline/`.

```
src/
├── config.py                   class đọc profile JSON trong config/
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
│   ├── config.py                   nạp config/sql.json
│   ├── offline.py                  parse -> chunk -> [link] -> embed -> index
│   └── online.py                   query -> hybrid -> RRF -> rerank
│
└── branch_rag_docs/            NHÁNH tài liệu PDF
    ├── config.py                   nạp config/rag_docs.json
    ├── offline.py                  parse -> [extract] -> chunk -> embed + index
    └── online.py                   query -> similarity -> rerank
```

`extract/` và `verify/` mới có chỗ đứng chứ chưa có nội dung cho nhánh SQL —
đó là hai chặng còn thiếu để chứng minh tri thức không mất mát. Xem docstring
trong `__init__.py` của từng chặng để biết cần bổ sung gì.

## config/ — profile

Tham số không nằm trong code. Mỗi bộ tài liệu là một **profile** JSON mô tả nó
được xử lý bằng cách nào. Khoá trong JSON đặt trùng tên với thư mục chặng trong
`src/offline/`, nên nhìn profile là biết chặng nào chạy với tham số gì.

```
config/
├── sql.json         parse docx · chunk theo heading · Vietnamese_Embedding + BM25 · Qdrant · hybrid
└── rag_docs.json    parse pdf  · chunk theo token   · bge-m3                     · Chroma · dense
```

```jsonc
{
  "kb": "sql",
  "parse":     { "loader": "docx_markitdown", "clean": { "block_injection": true } },
  "extract":   { "enabled": false, "extractor": "schema_extract" },
  "link":      { "enabled": false, "builder": "knowledge_graph" },
  "chunk":     { "mode": "structural", "headers": [["#","section"],["##","table"]], "overlap": 0 },
  "embed":     { "dense": { "model": "AITeamVN/Vietnamese_Embedding", "dim": 1024 },
                 "sparse": { "model": "Qdrant/bm25", "k": 1.2, "b": 0.0 } },
  "index":     { "store": "qdrant", "collection": "sqldocs__vnemb_1024__c1" },
  "retrieval": { "mode": "hybrid", "candidate_k": 20, "rrf_k": 40,
                 "rerank": { "model": "AITeamVN/Vietnamese_Reranker", "top_n": 5 } }
}
```

Đọc lên bằng class có kiểu, validate lúc nạp — sai khoá hay sai giá trị thì báo
ngay chứ không chạy sai âm thầm:

```python
from src.config import KBConfig
cfg = KBConfig.load("sql")
cfg.chunk.max_chars      # 6000
cfg.processed_dir        # <repo>/data/processed/sql
cfg.save()               # ghi ngược ra JSON, dùng khi người dùng chỉnh qua UI
```

Thêm cách xử lý mới thì thêm một file JSON, không phải sửa code:

```bash
cp config/sql.json config/sql_chunk_nho.json     # rồi sửa chunk.max_chars
VI_COZE_PROFILE=sql_chunk_nho uv run python -m src.branch_sql.offline "file.docx"
```

Đường dẫn **không** nằm trong JSON — suy ra từ `kb`, để profile không dính đường
dẫn tuyệt đối của máy nào. `QDRANT_URL` trong môi trường thắng giá trị trong file.

> Hiện profile được chọn lúc import qua biến môi trường. Muốn mỗi request chọn
> một profile khác nhau như Dify thì phải truyền `KBConfig` xuống thân hàm thay
> vì đọc hằng số module — đó là bước tiếp theo.

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

# vi-coze

Pipeline RAG tiếng Việt. Hai nhánh tài liệu, mỗi nhánh một bộ chặng xử lý riêng.

## Cấu trúc

Cây chia theo **bộ tài liệu** trước, trong mỗi nhánh mới chia theo **chức năng**.
Nhánh nào cũng có cùng ba phần: `config.py` nạp profile JSON, `offline/` nạp tri
thức, `online/` truy vấn. Thứ tự nối các chặng nằm ở `pipeline.py` của từng
luồng, không nằm ở các thư mục chặng.

Hai nhánh cùng tên chặng nhưng khác cách làm (docx/heading so với pdf/số trang,
Qdrant hybrid so với Chroma dense) nên không dùng chung module: sửa một nhánh
không đụng nhánh kia. Chỗ thật sự dùng chung chỉ còn `config.py` và `schemas.py`.

```
src/
├── config.py                   class đọc profile JSON trong config/
├── schemas.py                  hợp đồng chunk chung cho mọi nhánh
│
├── branch_sql/                 NHÁNH tài liệu mô tả schema CSDL (.docx)
│   ├── config.py                   nạp config/sql.json
│   ├── offline/                parse -> chunk -> [link] -> embed -> index
│   │   ├── pipeline.py             điều phối, nối bằng LCEL
│   │   ├── parse/
│   │   │   └── docx_parse.py           .docx -> markdown có heading
│   │   ├── extract/                    (CHƯA CÓ: markdown -> schema.json)
│   │   ├── link/
│   │   │   └── knowledge_graph.py      graph node-link, cờ --kg
│   │   ├── chunk/
│   │   │   └── table_chunker.py        1 bảng = 1 chunk, overlap 0
│   │   ├── embed/
│   │   │   ├── dense.py                dùng chung index + query
│   │   │   ├── sparse.py               BM25
│   │   │   └── kg_embedder.py          embed triple (prototype)
│   │   ├── index/
│   │   │   └── qdrant_store.py         dense + sparse -> Qdrant
│   │   └── verify/                     (CHƯA CÓ: coverage, trace)
│   └── online/                 query -> hybrid -> RRF -> rerank
│       ├── pipeline.py             điều phối
│       ├── qdrant_retriever.py     hybrid dense + BM25
│       ├── rerank.py               cross-encoder tiếng Việt
│       └── kg_retriever.py         truy hồi trên graph (prototype)
│
└── branch_rag_docs/            NHÁNH tài liệu PDF
    ├── config.py                   nạp config/rag_docs.json
    ├── offline/                parse -> [extract] -> chunk -> embed + index
    │   ├── pipeline.py             điều phối
    │   ├── parse/
    │   │   ├── pdf_parse.py            .pdf -> block có page/bbox
    │   │   ├── image_extractor.py      tách hình khỏi pdf     (cờ --images)
    │   │   └── image_captioner.py      sinh caption cho hình  (cờ --images)
    │   ├── extract/
    │   │   └── merge_documents.py      gộp text + caption theo trang
    │   ├── chunk/
    │   │   └── text_chunker.py         cắt theo token, có overlap
    │   ├── index/
    │   │   └── chroma_store.py         embed dense -> Chroma
    │   └── verify/
    │       └── inspect_chunks.py       thống kê phân bố chunk, chạy tay
    └── online/                 query -> similarity -> rerank
        ├── pipeline.py             điều phối
        ├── chroma_retriever.py     similarity search
        └── bge_reranker.py         cross-encoder bge
```

Thư mục chặng rỗng là chỗ đứng đã đặt sẵn chứ chưa có nội dung: nhánh SQL còn
thiếu `extract/` và `verify/` — hai chặng cần để chứng minh tri thức không mất
mát; nhánh PDF chưa có `link/`. Xem docstring trong `__init__.py` của từng chặng
để biết cần bổ sung gì.

## config/ — profile

Tham số không nằm trong code. Mỗi bộ tài liệu là một **profile** JSON mô tả nó
được xử lý bằng cách nào. Khoá trong JSON đặt trùng tên với thư mục chặng trong
`<nhánh>/offline/`, nên nhìn profile là biết chặng nào chạy với tham số gì.

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
uv run python -m src.branch_sql.offline.parse.docx_parse    "Mô tả bảng BĐS (NEW).docx"
uv run python -m src.branch_sql.offline.chunk.table_chunker mo_ta_bang_bds_new.md
uv run python -m src.branch_sql.offline.index.qdrant_store  mo_ta_bang_bds_new.chunks.jsonl
uv run python -m src.branch_sql.online.qdrant_retriever     "bảng nào lưu doanh thu TKC"
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

# vi-coze

Pipeline RAG tiếng Việt. Nhánh `khanh-dev` gộp công việc của cả ba nhánh cũ.

## Quy ước

Mỗi bộ tài liệu là một **nhánh**, đánh dấu bằng hậu tố tên file. Muốn chạy nhánh
SQL thì chỉ cần một entry point: `offline_sql.py` để nạp tri thức, `online_sql.py`
để truy vấn. Các bước xử lý nằm trong `src/retrieval/` và dùng chung.

```
src/
├── config_sql.py          # đường dẫn + mọi tham số của nhánh SQL
├── schemas.py             # ChunkMeta: hợp đồng metadata của chunk
├── offline_sql.py         # ENTRY: parse -> chunk -> [kg] -> embed -> Qdrant
├── online_sql.py          # ENTRY: query -> hybrid -> RRF -> rerank -> top-k
├── retrieval/             # các bước, mỗi bước một file, chạy độc lập được
│   ├── parse.py           #   .docx -> .md
│   ├── chunking.py        #   .md   -> .chunks.jsonl
│   ├── knowledge.py       #   .md   -> knowledge graph (node-link JSON + HTML)
│   ├── embeddings.py      #   dense, dùng chung index + query
│   ├── sparse.py          #   BM25, dùng chung index + query
│   ├── store.py           #   embed + upsert Qdrant
│   ├── retriever.py       #   hybrid search
│   ├── rerank.py          #   cross-encoder
│   ├── kg_embedder.py     #   (prototype) embed từng triple -> .npz
│   └── kg_retrieval.py    #   (prototype) truy hồi trên .npz
└── pdf/                   # nhánh tài liệu PDF — chưa có entry point *_pdf.py
```

Thư mục `sql/` ở ngoài cùng đã bỏ: `knowledge_graph_maker.py` thành
`src/retrieval/knowledge.py` và là một bước trong chain của `offline_sql.py`;
hai file còn lại thành `kg_embedder.py` / `kg_retrieval.py` cùng chỗ với các
bước khác.

## data/

Trước đây hai nhánh dùng hai cách đặt tên cho cùng một thứ — `uploads`/`artifacts`
và `raw`/`processed`. Nay chia theo **vai trò** trước, rồi mới theo bộ tài liệu:

```
data/
├── raw/<kb>/         # đầu vào người dùng cung cấp — pipeline không ghi vào
├── processed/<kb>/   # artifact sinh ra, xoá đi chạy lại được
├── index/            # vector store trên đĩa (chroma/, kb_index.npz)
└── eval/<kb>/        # bộ gold để đo độ chính xác
```

`<kb>` hiện có `sql` và `pdf`, khớp với `KB = "sql"` trong `config_sql.py`.

## Chạy

```bash
uv sync
docker compose up -d                 # Qdrant

# cả luồng: parse -> chunk -> embed -> upsert Qdrant
uv run python -m src.offline_sql "Mô tả bảng BĐS (NEW).docx"

# dừng ở chunk, không nạp model 2,2 GB — dùng khi tune chunking (~10 giây)
uv run python -m src.offline_sql "Mô tả bảng BĐS (NEW).docx" --no-index

# thêm bước dựng knowledge graph (cần `uv sync --extra kg` + ollama đang chạy)
uv run python -m src.offline_sql "Mô tả bảng BĐS (NEW).docx" --kg

uv run python -m src.online_sql "Bảng nào lưu doanh thu tài khoản chính?"
```

Từng bước vẫn chạy riêng được: `python -m src.retrieval.parse`,
`.chunking`, `.knowledge`, `.store`, `.retriever`.

Chi tiết: [docs/README-sql-pipeline.md](docs/README-sql-pipeline.md) ·
[docs/README-pdf-pipeline.md](docs/README-pdf-pipeline.md) ·
báo cáo kỹ thuật [report.md](report.md).

## Ba cách truy hồi đang tồn tại song song

Việc gộp nhánh làm lộ ra rằng repo có ba bản cài đặt cho cùng một việc. Chúng đã
nằm chung một cây thư mục nhưng **chưa hợp nhất về mặt kỹ thuật**.

| | `offline_sql` + `online_sql` | `kg_embedder` + `kg_retrieval` | `src/pdf` |
|---|---|---|---|
| Đơn vị index | cả bảng (1 bảng = 1 chunk) | từng triple của graph | đoạn ~1000 ký tự, overlap 150 |
| Dense model | `AITeamVN/Vietnamese_Embedding` (1024d) | `BAAI/bge-m3` | `BAAI/bge-m3` |
| Sparse | fastembed `Qdrant/bm25`, k=1.2 b=0 | `rank_bm25.BM25Okapi` trong RAM | không có |
| Hợp nhất | RRF phía Qdrant, hằng số 40 | RRF viết tay, hằng số 60 | không có |
| Reranker | `AITeamVN/Vietnamese_Reranker` | `BAAI/bge-reranker-v2-m3` | `BAAI/bge-reranker-v2-m3` |
| Store | Qdrant (docker) | `.npz` nạp vào RAM | Chroma (thư mục đĩa) |

Vector của ba bên **không so sánh được với nhau** vì khác model và khác đơn vị
index, nên không trộn kết quả được. Hai hằng số RRF khác nhau (40 và 60) cũng
cho thứ hạng khác nhau trên cùng tập ứng viên.

## Thư viện

Khai báo tập trung ở [pyproject.toml](pyproject.toml). `requirements.txt` của
nhánh `rag_phase3` đã gộp vào và xoá — nó khai báo 7 gói không import ở đâu
(`FlagEmbedding`, `pandas`, `beautifulsoup4`, `scikit-learn`, `tqdm`,
`python-dotenv`, `chromadb`) và thiếu 5 gói đang import thật (`docling`,
`tiktoken`, `pillow`, `transformers`, cùng nhóm `openai`/`networkx`/`pyvis`/
`rank-bm25` của knowledge graph). Cài theo file đó thì `src/pdf/pdf_loader.py`
không chạy được vì thiếu `docling`.

Phần thực sự dùng chung giữa ba bên chỉ có `langchain-core` và
`sentence-transformers`.

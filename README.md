# vi-coze

Nhánh `khanh-dev` hợp nhất công việc của cả ba nhánh. Repo hiện chứa **hai
pipeline RAG độc lập**, chưa nối vào nhau:

| | Pipeline schema SQL | Pipeline PDF |
|---|---|---|
| Nguồn | `.docx` mô tả bảng CSDL (tiếng Việt) | `.pdf` |
| Code | `src/retrieval/`, `src/offline_sql.py`, `src/online_sql.py`, `sql/` | `src/data/`, `src/rag/` |
| Chunking | theo heading markdown, 1 bảng = 1 chunk | `src/data/chunker_optimized.py` |
| Embedding | `AITeamVN/Vietnamese_Embedding` + BM25 | `BAAI/bge-m3` |
| Vector store | Qdrant (`docker compose up -d`) | Chroma (`data/vectorstore/chroma/`) |
| Rerank | `AITeamVN/Vietnamese_Reranker` | `src/rag/reranker.py` |
| Quản lý gói | `pyproject.toml` + `uv.lock` (uv) | `requirements.txt` (pip) |
| Tài liệu | [docs/README-sql-pipeline.md](docs/README-sql-pipeline.md) | [docs/README-pdf-pipeline.md](docs/README-pdf-pipeline.md) |

Cả hai đều dừng ở tầng truy hồi — không gọi LLM, chưa có bước sinh câu trả lời
hay sinh SQL.

Báo cáo kỹ thuật của pipeline schema SQL: [report.md](report.md).

## Cần hợp nhất tiếp

Hai pipeline đang trùng vai trò và chưa dùng chung gì:

- hai vector store (Qdrant và Chroma), hai bộ embedding/rerank model khác nhau
- hai cách khai báo dependency (`uv` và `pip`) — cài theo một cách sẽ thiếu gói
  của cách kia
- `src/rag/retriever.py` và `src/retrieval/retriever.py` là hai bản cài đặt
  riêng của cùng một khái niệm
- nhánh knowledge graph trong `sql/` (`knowledge_graph_maker.py` →
  `embedder.py` → `kb_index.npz`) lại là một hệ truy hồi thứ ba, tách khỏi cả hai

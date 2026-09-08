---
name: langchain-rag
description: Xây RAG pipeline với LangChain — document loader, text splitter, embedding, vector store (Chroma/FAISS/Qdrant/pgvector), retriever, hybrid search, rerank, và RAG chain. Bao gồm xử lý PDF và tài liệu tiếng Việt. Dùng khi task nhắc tới RAG, ingestion, chunking, embedding, vector store, retriever, rerank, hoặc khi sửa file có loader/splitter/vectorstore.
---

# RAG với LangChain

**Chạy `uv pip show langchain-core langchain-text-splitters` trước khi viết.**

## Kiến trúc và nguyên tắc tách tầng

```
load -> split -> embed -> store        (ingestion, offline)
query -> retrieve -> rerank -> generate (serving, online)
```

**Tầng retrieve không được gọi LLM.** Giữ được ranh giới này thì đo được chất
lượng truy hồi bằng recall@k / MRR mà không tốn token — chỉnh chunking hay đổi
embedding model là chạy eval rẻ tiền, không phải chạy cả pipeline đắt.

## Load

```python
from langchain_community.document_loaders import PyPDFLoader, DirectoryLoader

docs = DirectoryLoader("data/", glob="**/*.pdf", loader_cls=PyPDFLoader).load()
```

| Nguồn | Loader |
|---|---|
| PDF text | `PyPDFLoader` (nhanh), `PyMuPDFLoader` (giữ layout tốt hơn) |
| PDF scan / ảnh | Cần OCR trước — `UnstructuredPDFLoader` với `strategy="ocr_only"` |
| Markdown / text | `TextLoader` (nhớ `encoding="utf-8"`) |
| Web | `WebBaseLoader` |
| CSV | `CSVLoader` |

**Kiểm tra output trước khi chạy tiếp.** PDF scan trả về `page_content` rỗng là
lỗi thầm lặng phổ biến nhất trong RAG — cả pipeline chạy sạch mà index rỗng:

```python
empty = [d for d in docs if len(d.page_content.strip()) < 50]
if empty:
    raise ValueError(f"{len(empty)} trang rỗng — nhiều khả năng là PDF scan, cần OCR")
```

## Split

```python
from langchain_text_splitters import RecursiveCharacterTextSplitter

splitter = RecursiveCharacterTextSplitter(
    chunk_size=1000,
    chunk_overlap=150,
    separators=["\n\n", "\n", ". ", " ", ""],   # thử lần lượt, giữ ranh giới ngữ nghĩa
)
chunks = splitter.split_documents(docs)
```

`RecursiveCharacterTextSplitter` là mặc định đúng cho ~90% trường hợp. Dùng khác
khi: Markdown có cấu trúc rõ → `MarkdownHeaderTextSplitter` (giữ heading vào
metadata); code → `RecursiveCharacterTextSplitter.from_language()`.

Cỡ chunk là đánh đổi, không có số đúng tuyệt đối:

| chunk_size | Được | Mất |
|---|---|---|
| 300–500 | Retrieval chính xác, ít nhiễu | Mất ngữ cảnh, câu trả lời vụn |
| 800–1200 | Cân bằng — **bắt đầu ở đây** | |
| 2000+ | Ngữ cảnh đầy đủ | Embedding loãng, tốn token, recall giảm |

`chunk_overlap` khoảng 10–20% `chunk_size`. Chốt bằng eval, không bằng cảm tính.

**Metadata quyết định khả năng filter về sau** — thêm ngay lúc split, thêm sau
là phải index lại:

```python
for c in chunks:
    c.metadata.update({
        "source": c.metadata["source"],
        "doc_type": "legal",
        "effective_date": "2024-01-01",
    })
```

## Embed

```python
from langchain_huggingface import HuggingFaceEmbeddings

embeddings = HuggingFaceEmbeddings(
    model_name="intfloat/multilingual-e5-base",
    encode_kwargs={"normalize_embeddings": True},
)
```

**Tiếng Việt:** model tiếng Anh thuần (`all-MiniLM-L6-v2`) cho kết quả kém rõ
rệt. Ưu tiên multilingual (`multilingual-e5-base/large`, `bge-m3`) hoặc model
huấn luyện riêng cho tiếng Việt. Model họ E5 yêu cầu prefix `"query: "` /
`"passage: "` — thiếu prefix là mất điểm số đáng kể mà không có lỗi nào báo.

**Đổi embedding model = đổi không gian vector.** Phải index lại toàn bộ; không
trộn hai model trong một collection. Ghi tên model vào metadata của collection
để phát hiện lệch.

## Store

| Store | Chọn khi |
|---|---|
| `Chroma` | Dev, prototype, dữ liệu nhỏ. Persistent local, không cần service |
| `FAISS` | In-memory, tốc độ cao, không cần filter phức tạp |
| `Qdrant` | Production, cần filter theo metadata mạnh, hybrid search |
| `PGVector` | Đã có Postgres — bớt một hạ tầng phải vận hành |

```python
from langchain_chroma import Chroma

store = Chroma(
    collection_name="vi_coze",
    embedding_function=embeddings,
    persist_directory=".vector_store",
)
store.add_documents(chunks)          # dùng add_documents, không loop add_document
```

Ingest số lượng lớn thì chia batch (~100–500 doc/lần) — nhồi một phát dễ OOM
hoặc timeout.

## Retrieve

```python
retriever = store.as_retriever(
    search_type="mmr",                       # đa dạng hóa kết quả
    search_kwargs={"k": 5, "fetch_k": 20, "filter": {"doc_type": "legal"}},
)
```

| `search_type` | Hành vi |
|---|---|
| `"similarity"` | Top-k gần nhất. Mặc định |
| `"mmr"` | Cân bằng liên quan và đa dạng — tránh 5 chunk gần trùng nhau |
| `"similarity_score_threshold"` | Cắt theo ngưỡng điểm; trả rỗng nếu không đủ tốt |

**Hybrid search** (dense + keyword) gần như luôn thắng dense thuần khi truy vấn
chứa mã số, tên riêng, thuật ngữ luật:

```python
from langchain_community.retrievers import BM25Retriever
from langchain.retrievers import EnsembleRetriever

hybrid = EnsembleRetriever(
    retrievers=[store.as_retriever(search_kwargs={"k": 10}), BM25Retriever.from_documents(chunks, k=10)],
    weights=[0.6, 0.4],
)
```

**Rerank** — lấy dư rồi để cross-encoder chọn lại, thường là cải thiện lớn nhất
với chi phí nhỏ nhất:

```python
from langchain.retrievers import ContextualCompressionRetriever
from langchain_community.document_compressors import FlashrankRerank

retriever = ContextualCompressionRetriever(
    base_retriever=hybrid,           # lấy k=20
    base_compressor=FlashrankRerank(top_n=5),
)
```

## Generate

```python
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnablePassthrough
from langchain_core.output_parsers import StrOutputParser

prompt = ChatPromptTemplate.from_template(
    """Trả lời câu hỏi CHỈ dựa trên các đoạn tài liệu dưới đây.
Đặt [số] ngay sau câu dùng thông tin từ đoạn đó.
Nếu tài liệu không đủ, nói rõ phần nào còn thiếu thay vì suy đoán.

<documents>
{context}
</documents>

Câu hỏi: {question}"""
)

def format_docs(docs):
    return "\n\n".join(
        f'[{i}] source={d.metadata.get("source")}\n{d.page_content}'
        for i, d in enumerate(docs, 1)
    )

chain = (
    {"context": retriever | format_docs, "question": RunnablePassthrough()}
    | prompt | model | StrOutputParser()
)
```

Ba điều bắt buộc trong prompt RAG: **chỉ dùng tài liệu được cấp**, **trích dẫn
theo số**, **được phép nói không biết**. Thiếu điều thứ ba là mời model bịa.

Cần trả về citation có cấu trúc thay vì text → dùng `.with_structured_output()`
(xem skill `langchain-core`).

## Agentic RAG

Khi retrieve một phát không đủ (câu hỏi multi-hop, cần tự đánh giá và thử lại),
chuyển sang graph: `retrieve → grade → (generate | rewrite → retrieve)`. Có vòng
lặp và state thì đọc skill `langgraph-workflows` — đừng nhét vòng lặp vào LCEL.

## Lỗi hay gặp

| Triệu chứng | Nguyên nhân |
|---|---|
| Retrieve trả rỗng / vô nghĩa | Index rỗng vì PDF scan không OCR |
| Điểm số thấp đều với model E5 | Thiếu prefix `"query: "` / `"passage: "` |
| Kết quả tệ sau khi đổi model | Chưa index lại — vector cũ khác không gian |
| 5 chunk gần trùng nhau | Dùng `similarity` thay vì `mmr` |
| Trượt truy vấn có mã số / tên riêng | Thiếu BM25 — cần hybrid |
| Filter metadata không ăn | Metadata thêm sau khi index |
| Model bịa dù có tài liệu | Prompt không cấm suy đoán và không cho phép nói không biết |
| Ingestion rất chậm | Loop `add_documents` từng cái, hoặc embed không batch |

## Trước khi kết thúc task

- Có assert kiểm tra chunk rỗng sau khi load.
- `chunk_size` / `chunk_overlap` / `k` đọc từ config, không hardcode rải rác —
  chúng là tham số cần tune.
- Tên embedding model ghi lại cùng collection.
- Có đường chạy eval retrieval riêng, không phải lúc nào cũng phải gọi LLM.

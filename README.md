# 🛡️ Vietnamese Legal Chatbot with Prompt Guard & Advanced RAG

Hệ thống tra cứu và hỏi đáp văn bản Pháp luật Việt Nam ứng dụng kỹ thuật **RAG đa tầng (Multi-Stage Retrieval & Specialized Legal Reranking)** kết hợp tầng phòng thủ bảo mật **Prompt Guard** chống tấn công Prompt Injection / Jailbreak.

---

## 🏛️ 1. Kiến trúc hệ thống (System Architecture)

```text
                           [ USER QUERY ]
                                 │
                                 ▼
                     ┌───────────────────────┐
                     │     Prompt Guard      │ ──► [Phát hiện Injection / Attack] ──► CHẶN
                     └───────────────────────┘
                                 │ (Safe)
                                 ▼
                     ┌───────────────────────┐
                     │    Vector Retrieval   │ ──► Embedding (BAAI/bge-m3)
                     │     (ChromaDB Top 30) │ ──► Lọc văn bản còn hiệu lực
                     └───────────────────────┘
                                 │
                                 ▼
                     ┌───────────────────────┐
                     │   Semantic Reranker   │ ──► Cross-Encoder (bge-reranker-v2-m3)
                     │       (Top 20)        │
                     └───────────────────────┘
                                 │
                                 ▼
                     ┌───────────────────────┐
                     │  Legal Score Ranker   │ ──► 65% Điểm ngữ nghĩa (Reranker)
                     │        (Top 5)        │ ──► 20% Độ mới văn bản (Recency Decay)
                     └───────────────────────┘ ──► 15% Thứ bậc hiệu lực (Hiến pháp > Luật > Nghị định...)
                                 │
                                 ▼
                     ┌───────────────────────┐
                     │    Context Builder    │ ──► Gắn System Prompt + Điều khoản trích dẫn
                     │      & LLM Engine     │
                     └───────────────────────┘
                                 │
                                 ▼
                     [ CÂU TRẢ LỜI & CĂN CỨ PHÁP LÝ ]
```

---

## 📂 2. Cấu trúc thư mục dự án (Project Structure)

```text
legal-chatbot-prompt-guard/
│
├── data/
│   ├── raw/                 # Chứa dữ liệu gốc (vietnamese_legal_content.jsonl, metadata.csv)
│   └── processed/           # Chứa dữ liệu sau khi làm sạch & chunking (active_clean.jsonl, chunked.jsonl)
│
├── chroma_legal_db/         # Thư mục lưu cơ sở dữ liệu Vector ChromaDB
│
├── src/
│   ├── __init__.py
│   │
│   ├── data/                # TẦNG 1: Xử lý và tiền xử lý dữ liệu
│   │   ├── __init__.py
│   │   ├── cleaner.py       # Bóc tách HTML, chuẩn hóa Unicode NFC, lọc văn bản còn hiệu lực
│   │   └── chunker.py       # Cắt văn bản theo từng Điều, gắn bối cảnh metadata vào từng chunk
│   │
│   ├── rag/                 # TẦNG 2: Core RAG Engine
│   │   ├── __init__.py
│   │   ├── indexer.py       # Nhúng vector (BGE-M3) và lưu vào ChromaDB (hỗ trợ Auto-resume)
│   │   ├── retriever.py     # Tìm kiếm Top-K vector tương đồng (tự động nhận GPU/CPU)
│   │   ├── reranker.py      # Cross-Encoder Reranker chấm lại điểm ngữ nghĩa chính xác
│   │   └── legal_ranker.py  # Thuật toán xếp hạng đặc thù: Độ mới + Thứ bậc hiệu lực pháp lý
│   │
│   └── guard/               # TẦNG 3: Kiểm soát an toàn & Prompt Guard
│       ├── __init__.py
│       └── prompt_guard.py  # Bộ lọc chống tấn công Prompt Injection, System Prompt Leak, Jailbreak
│
├── tests/                   # Kịch bản kiểm thử chức năng
│   ├── __init__.py
│   ├── test_guard.py        # Kiểm thử các trường hợp tấn công prompt
│   ├── test_retriever.py    # Kiểm thử riêng tầng Vector Search
│   └── test_pipeline.py     # Kiểm thử toàn diện toàn bộ luồng RAG + Security
│
├── .gitignore               # Loại bỏ dữ liệu lớn, database và môi trường ảo khỏi Git
├── Dockerfile               # Cấu hình containerization
├── requirements.txt         # Danh sách thư viện phụ thuộc
└── README.md                # Tài liệu hướng dẫn sử dụng
```

---

## ⚙️ 3. Cài đặt môi trường (Installation)

### Yêu cầu hệ thống:
- Python 3.10 hoặc 3.11
- Dung lượng RAM tối thiểu 8GB (Khuyến nghị có GPU NVIDIA với VRAM >= 6GB để tăng tốc độ embedding & reranking).

### Bước 1: Tạo và kích hoạt môi trường ảo

```powershell
# Tạo môi trường ảo
python -m venv .venv

# Kích hoạt môi trường ảo trên Windows (PowerShell)
.\.venv\Scripts\Activate.ps1
```

### Bước 2: Cài đặt thư viện

Nếu máy có **GPU NVIDIA (CUDA 11.8 / 12.x)**:
```powershell
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu118
pip install -r requirements.txt
```

Nếu máy chỉ có **CPU**:
```powershell
pip install -r requirements.txt
```

---

## 🚀 4. Hướng dẫn chạy từng bước (Step-by-Step Pipeline)

### Bước 1: Làm sạch dữ liệu và lọc hiệu lực (`cleaner.py`)
Đặt file nội dung thô `vietnamese_legal_content.jsonl` và `metadata.csv` vào thư mục `data/raw/`:

```powershell
python -m src.data.cleaner --input data/raw/vietnamese_legal_content.jsonl --metadata data/raw/metadata.csv --output-dir data/processed
```
*Kết quả:* Tạo ra file `data/processed/vietnamese_legal_active_clean.jsonl` chứa các văn bản còn hiệu lực đã làm sạch HTML và chuẩn hóa Unicode.

---

### Bước 2: Phân đoạn văn bản (`chunker.py`)
Cắt văn bản theo từng **Điều**, tự động gắn header thông tin (Tên VB, Số hiệu, Cơ quan, Ngày ban hành):

```powershell
python -m src.data.chunker --input data/processed/vietnamese_legal_active_clean.jsonl --output data/processed/chunked.jsonl
```
*Kết quả:* Tạo ra file `data/processed/chunked.jsonl`.

---

### Bước 3: Nhúng vector và lưu vào ChromaDB (`indexer.py`)
Mô hình `BAAI/bge-m3` sẽ đọc các chunk, tạo embeddings và lưu vào thư mục `chroma_legal_db/`:

```powershell
python -m src.rag.indexer --input data/processed/chunked.jsonl --db-dir chroma_legal_db --batch-size 5000
```
> **Tính năng Auto-Resume:** Nếu quá trình nhúng bị ngắt quãng giữa chừng, script sẽ tự động kiểm tra số bản ghi đã có trong DB và tiếp tục chạy từ vị trí đó.

---

### Bước 4: Kiểm thử hệ thống

#### 1. Kiểm thử tầng bảo mật Prompt Guard:
```powershell
python -m tests.test_guard
```

#### 2. Kiểm thử riêng tầng Vector Search:
```powershell
python -m tests.test_retriever --query "Luật Doanh nghiệp 2020" --top-k 10
```

#### 3. Kiểm thử toàn bộ Pipeline hoàn chỉnh (Guard -> Retrieve -> Rerank -> Legal Score):
```powershell
python -m tests.test_pipeline --query "Người dưới 18 tuổi có được thành lập doanh nghiệp không?"
```

---

## 📊 5. Thuật toán Xếp hạng Pháp lý chuyên sâu (Legal Ranking)

Khác với các hệ thống RAG thông thường chỉ so sánh độ tương đồng từ ngữ, hệ thống áp dụng công thức chấm điểm đa tiêu chí:

$$\text{Score}_{\text{Final}} = 0.65 \times \text{Score}_{\text{Reranker}} + 0.20 \times \text{Score}_{\text{Recency}} + 0.15 \times \text{Score}_{\text{Hierarchy}}$$

1. **Điểm Ngữ nghĩa ($\text{Score}_{\text{Reranker}}$ - 65%)**: Được tính toán qua mô hình Cross-Encoder `BAAI/bge-reranker-v2-m3`.
2. **Điểm Độ mới ($\text{Score}_{\text{Recency}}$ - 20%)**: Sử dụng hàm suy giảm số mũ:
   $$\text{Score}_{\text{Recency}} = e^{-0.07 \times \text{Tuổi văn bản (năm)}}$$
   *(Văn bản sau 10 năm điểm giảm còn ~50% so với văn bản mới ban hành).*
3. **Điểm Thứ bậc hiệu lực ($\text{Score}_{\text{Hierarchy}}$ - 15%)**:
   - Hiến pháp: `1.0`
   - Bộ luật / Luật: `0.95`
   - Nghị quyết: `0.85`
   - Nghị định: `0.75`
   - Thông tư: `0.65`
   - Quyết định / Chỉ thị: `0.35 - 0.45`

---

## 🛡️ 6. Cơ chế phòng thủ Prompt Guard

Module `src/guard/prompt_guard.py` đảm bảo kiểm soát an toàn trước khi query đến các tầng sau:
- **Instruction Override**: Ngăn chặn câu lệnh yêu cầu "bỏ qua chỉ dẫn trước đó", "ignore previous instructions".
- **System Prompt Leak**: Ngăn chặn yêu cầu tiết lộ câu lệnh hệ thống nội bộ.
- **Jailbreak Modes**: Phát hiện chế độ DAN, Developer mode, Unrestricted mode.
- **Code/SQL Injection**: Loại bỏ các thẻ script và cú pháp injection nguy hiểm.

---

## 🐳 7. Chạy với Docker

```powershell
# Build image
docker build -t legal-chatbot-guard .

# Chạy container kiểm thử pipeline
docker run --rm legal-chatbot-guard
```

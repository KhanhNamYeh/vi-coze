---
name: langsmith-eval
description: Đánh giá và giám sát app LangChain/LangGraph — LangSmith tracing, dataset, evaluate(), LLM-as-judge, custom evaluator, và RAGAS cho RAG. Dùng khi task nhắc tới eval, evaluation, đánh giá, LangSmith, tracing, dataset, judge, RAGAS, recall@k, hoặc khi cần đo chất lượng retrieval / câu trả lời.
---

# Evaluation & tracing

**Chạy `uv pip show langsmith` trước khi viết.**

> **Đang eval agent, không phải RAG?** Skill này đo *output*. Agent còn phải đo
> **trajectory** (chuỗi hành động: chọn tool, số bước, phục hồi lỗi) — xem skill
> `agent-production`. Agent trả lời đúng nhờ đi vòng 12 bước vẫn là agent hỏng.

## Đo cái gì, ở tầng nào

Tách hai tầng — trộn lại là không biết hỏng ở đâu:

| Tầng | Metric | Cần LLM? | Chạy khi |
|---|---|---|---|
| **Retrieval** | recall@k, MRR, nDCG, hit rate | Không | Mỗi lần đổi chunking / embedding / k |
| **Generation** | faithfulness, relevancy, correctness | Có | Trước khi release, khi đổi prompt / model |

Đổi `chunk_size` mà recall@k tụt thì dừng ngay, không cần chạy tiếp phần tốn
token. Đây là lý do retriever không được gọi LLM (xem skill `langchain-rag`).

## Retrieval eval — không cần LangSmith, không cần LLM

Rẻ, nhanh, chạy được trong CI:

```python
def recall_at_k(retriever, dataset: list[dict], k: int = 5) -> float:
    """dataset: [{"question": str, "relevant_sources": list[str]}, ...]"""
    hits = 0
    for row in dataset:
        got = {d.metadata["source"] for d in retriever.invoke(row["question"])[:k]}
        if got & set(row["relevant_sources"]):
            hits += 1
    return hits / len(dataset)
```

Bộ 30–50 câu hỏi có nhãn nguồn đúng là đủ để bắt regression. Ghi kết quả ra thư
mục output (gitignore), không ghi vào thư mục dữ liệu nguồn.

## Tracing

```bash
export LANGSMITH_TRACING=true
export LANGSMITH_API_KEY=lsv2_...
export LANGSMITH_PROJECT=vi-coze-dev
```

Đặt env là mọi Runnable, chain, graph tự động được trace — không phải sửa code.
Hàm thường thì bọc thêm:

```python
from langsmith import traceable

@traceable(run_type="retriever")
def custom_search(query: str) -> list[dict]:
    ...
```

Gắn metadata để lọc trên UI và so sánh giữa các lần chạy:

```python
chain.invoke(x, config={
    "metadata": {"model": "sonnet-4-5", "k": 5, "chunk_size": 1000},
    "tags": ["prod", "vi"],
    "run_name": "rag-answer",
})
```

**Tách project theo môi trường** (`vi-coze-dev` / `vi-coze-prod`) — trộn trace
dev vào prod là mất khả năng đọc số liệu thật.

## Dataset

```python
from langsmith import Client

client = Client()
ds = client.create_dataset("legal-qa-v1")
client.create_examples(
    dataset_id=ds.id,
    inputs=[{"question": q} for q in questions],
    outputs=[{"answer": a} for a in answers],
)
```

Đánh version dataset trong tên (`-v1`, `-v2`). So sánh hai lần chạy trên hai
dataset khác nhau là so sánh vô nghĩa.

## evaluate()

```python
from langsmith import evaluate

def correctness(outputs: dict, reference_outputs: dict) -> dict:
    ok = reference_outputs["answer"].lower() in outputs["answer"].lower()
    return {"key": "correctness", "score": float(ok)}

results = evaluate(
    lambda inputs: {"answer": chain.invoke(inputs["question"])},
    data="legal-qa-v1",
    evaluators=[correctness, faithfulness_judge],
    experiment_prefix="rerank-on",
    max_concurrency=8,
)
```

`experiment_prefix` là thứ cho phép so sánh cạnh nhau trên UI — đặt tên theo
**điều đang thay đổi** (`rerank-on`, `chunk-500`, `sonnet-vs-haiku`), không phải
theo ngày.

**Mỗi lần chỉ đổi một biến.** Đổi cùng lúc chunk_size và model thì kết quả không
quy trách nhiệm được cho ai.

## LLM-as-judge

```python
from pydantic import BaseModel, Field

class Grade(BaseModel):
    score: int = Field(ge=1, le=5, description="1 = bịa hoàn toàn, 5 = mọi câu đều có căn cứ")
    reasoning: str

judge = judge_model.with_structured_output(Grade)

def faithfulness_judge(inputs: dict, outputs: dict) -> dict:
    g = judge.invoke(
        f"Tài liệu:\n{outputs['context']}\n\n"
        f"Câu trả lời:\n{outputs['answer']}\n\n"
        "Chấm: mọi khẳng định trong câu trả lời có được tài liệu chống lưng không?"
    )
    return {"key": "faithfulness", "score": g.score / 5, "comment": g.reasoning}
```

Quy tắc dùng judge:

- **Structured output bắt buộc** — parse text của judge bằng regex là tự chuốc lỗi.
- **Rubric cụ thể**, gắn với hành vi quan sát được. "Chấm chất lượng 1–5" cho
  điểm nhiễu; "1 = có khẳng định không nằm trong tài liệu" thì cho điểm ổn định.
- **Judge dùng model mạnh hơn hoặc ngang** model đang chấm.
- **Hiệu chỉnh judge trước khi tin nó**: tự tay chấm 20 mẫu, so với judge. Lệch
  nhiều thì sửa rubric, chưa dùng để ra quyết định.
- Chấm riêng từng khía cạnh (faithfulness, relevancy, completeness), đừng gộp
  thành một điểm tổng.

## RAGAS

Bộ metric RAG dựng sẵn, dùng khi muốn số liệu chuẩn hóa thay vì tự viết judge:

| Metric | Đo gì | Cần ground truth? |
|---|---|---|
| `faithfulness` | Câu trả lời có bám tài liệu không (chống bịa) | Không |
| `answer_relevancy` | Có trả lời đúng câu hỏi không | Không |
| `context_precision` | Chunk lấy về có liên quan không | Không |
| `context_recall` | Có lấy đủ chunk cần thiết không | **Có** |

Hai metric đầu chạy được ngay không cần nhãn — bắt đầu từ đó. `context_recall`
cần dataset có đáp án chuẩn.

RAGAS gọi LLM cho từng mẫu, tốn tiền và chậm — chạy trên tập 50–100 mẫu ở CI
nightly, không chạy mỗi commit.

## Lỗi hay gặp

| Triệu chứng | Nguyên nhân |
|---|---|
| Không thấy trace | Thiếu `LANGSMITH_TRACING=true`, hoặc sai API key |
| Trace thiếu bước giữa | Hàm thường chưa bọc `@traceable` |
| Điểm judge nhiễu, chạy lại ra khác | Rubric mơ hồ; hoặc judge không dùng structured output |
| Eval rất chậm | Thiếu `max_concurrency`, hoặc dùng `.invoke` thay `.batch` |
| Cải thiện metric nhưng người dùng thấy tệ hơn | Dataset không đại diện dữ liệu thật |
| Không biết thay đổi nào gây regression | Đổi nhiều biến trong một experiment |

## Trước khi kết thúc task

- Retrieval eval chạy được **độc lập**, không gọi LLM.
- Mỗi experiment đổi đúng một biến, có `experiment_prefix` mô tả biến đó.
- Judge có rubric cụ thể + structured output, và đã được đối chiếu tay ít nhất một lần.
- Kết quả eval ghi ra thư mục output (gitignore), không lẫn vào dữ liệu nguồn.

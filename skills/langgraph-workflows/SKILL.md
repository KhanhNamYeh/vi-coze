---
name: langgraph-workflows
description: Xây workflow nhiều bước bằng LangGraph — StateGraph, node/edge, conditional edge, state reducer, checkpointer và thread, human-in-the-loop bằng interrupt, streaming, subgraph, map-reduce bằng Send. Dùng khi task nhắc tới LangGraph, StateGraph, graph, node, edge, checkpointer, thread_id, interrupt, Command, agentic RAG, Self-RAG, CRAG, multi-agent, hoặc khi đang sửa file import từ langgraph.
---

# LangGraph workflows

Viết theo `langgraph>=1.0`. **Chạy `uv pip show langgraph` trước khi viết.**

## Chọn đúng công cụ trước

| Bài toán | Dùng |
|---|---|
| Prompt → model → parse, một lượt | LCEL thuần (`langchain-core`) |
| Model tự quyết gọi tool, vòng lặp ReAct chuẩn | `create_agent` (`langchain-core`) |
| Luồng cố định nhiều bước, có rẽ nhánh theo điều kiện của bạn | **StateGraph** |
| Cần state ngoài `messages` (documents, retry count, grade) | **StateGraph** |
| Cần dừng giữa chừng chờ người duyệt, rồi chạy tiếp | **StateGraph + checkpointer** |
| Nhiều agent phối hợp | **StateGraph** (supervisor / handoff) |

Đừng bọc StateGraph quanh thứ mà `create_agent` làm được — thêm code, thêm chỗ hỏng.

## State — thiết kế trước, code sau

State là nơi mọi thứ hỏng nếu làm sai. Node **trả về dict cập nhật một phần**,
không phải state đầy đủ.

```python
from typing import Annotated, TypedDict
from operator import add
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langchain_core.documents import Document

class RAGState(TypedDict):
    question: str
    messages: Annotated[list, add_messages]   # gộp, giữ id, không đè
    documents: list[Document]                  # không có reducer -> GHI ĐÈ
    grades: Annotated[list[str], add]          # nối thêm
    retries: int
```

Quy tắc reducer:

- **Không có `Annotated`** → giá trị mới **ghi đè** giá trị cũ. Đây là mặc định
  và đúng cho phần lớn field.
- `Annotated[list, add]` → nối thêm. Dùng cho log, grade, kết quả tích lũy.
- `Annotated[list, add_messages]` → gộp message theo `id`, xử lý được cả
  `RemoveMessage`. **Luôn dùng cái này cho `messages`**, đừng dùng `add`.

Hai lỗi kinh điển:
1. Dùng `add` cho `messages` → message trùng lặp, tool_call_id lệch, model rối.
2. Quên reducer cho field mà nhiều node cùng ghi (nhánh song song) →
   `InvalidUpdateError`. Có fan-out là phải có reducer.

## Node và edge

Node là hàm thuần: nhận state, trả dict cập nhật.

```python
def retrieve(state: RAGState) -> dict:
    docs = retriever.invoke(state["question"])
    return {"documents": docs}          # chỉ trả field mình đổi

def grade(state: RAGState) -> dict:
    keep = [d for d in state["documents"] if is_relevant(d, state["question"])]
    return {"documents": keep, "grades": [f"{len(keep)}/{len(state['documents'])}"]}

def generate(state: RAGState) -> dict:
    answer = rag_chain.invoke({"context": state["documents"], "question": state["question"]})
    return {"messages": [answer]}
```

Rẽ nhánh bằng hàm trả về **tên node kế tiếp**:

```python
def decide(state: RAGState) -> str:
    if state["documents"]:
        return "generate"
    if state["retries"] >= 2:
        return "fallback"
    return "rewrite_query"

builder = StateGraph(RAGState)
builder.add_node("retrieve", retrieve)
builder.add_node("grade", grade)
builder.add_node("rewrite_query", rewrite_query)
builder.add_node("generate", generate)
builder.add_node("fallback", fallback)

builder.add_edge(START, "retrieve")
builder.add_edge("retrieve", "grade")
builder.add_conditional_edges("grade", decide, ["generate", "rewrite_query", "fallback"])
builder.add_edge("rewrite_query", "retrieve")     # vòng lặp
builder.add_edge("generate", END)
builder.add_edge("fallback", END)

graph = builder.compile()
```

Danh sách đích thứ ba trong `add_conditional_edges` là để vẽ sơ đồ đúng — luôn
truyền vào. **Mọi vòng lặp phải có điều kiện thoát đếm được** (`retries`), nếu
không graph chạy tới `GraphRecursionError`.

`Command` gộp "cập nhật state" và "đi đâu tiếp" vào một chỗ — hữu ích cho
multi-agent handoff:

```python
from langgraph.types import Command
from typing import Literal

def supervisor(state) -> Command[Literal["researcher", "writer", "__end__"]]:
    nxt = pick_next(state)
    return Command(goto=nxt, update={"log": [f"-> {nxt}"]})
```

## Checkpointer và thread

Không có checkpointer thì graph không nhớ gì giữa các lần `invoke`, và
`interrupt` không hoạt động.

```python
from langgraph.checkpoint.memory import InMemorySaver

graph = builder.compile(checkpointer=InMemorySaver())

config = {"configurable": {"thread_id": "user-42"}}
graph.invoke({"question": "..."}, config)
graph.invoke({"question": "câu hỏi tiếp"}, config)   # thấy lại state cũ
```

| Checkpointer | Dùng cho |
|---|---|
| `InMemorySaver` | Test, notebook. **Mất khi restart** |
| `SqliteSaver` | Dev local, app một máy |
| `PostgresSaver` | Production. Phải gọi `.setup()` một lần để tạo bảng |

`thread_id` chính là session id. Cùng `thread_id` = cùng cuộc hội thoại. Kiểm
tra state hiện tại bằng `graph.get_state(config)`, xem lịch sử bằng
`graph.get_state_history(config)` (dùng để time-travel / debug).

## Human-in-the-loop

`interrupt()` dừng graph tại chỗ và trả quyền cho code gọi:

```python
from langgraph.types import interrupt, Command

def confirm_delete(state) -> dict:
    decision = interrupt({
        "action": "delete_records",
        "count": len(state["targets"]),
    })
    if decision != "approve":
        return {"messages": [("assistant", "Đã hủy theo yêu cầu.")]}
    return {"messages": [("assistant", do_delete(state["targets"]))]}
```

Phía gọi:

```python
result = graph.invoke(inputs, config)
if "__interrupt__" in result:
    payload = result["__interrupt__"][0].value      # đưa ra UI cho người duyệt
    result = graph.invoke(Command(resume="approve"), config)
```

Hai điều bắt buộc: **phải có checkpointer**, và **code trước `interrupt()` trong
node sẽ chạy lại** khi resume — nên đừng đặt side effect (ghi DB, gửi mail)
trước lệnh `interrupt` trong cùng một node.

## Streaming

```python
for mode, chunk in graph.stream(inputs, config, stream_mode=["updates", "messages"]):
    ...
```

| `stream_mode` | Trả về | Dùng khi |
|---|---|---|
| `"updates"` | Dict cập nhật sau mỗi node | Hiện tiến độ "đang retrieve…" |
| `"values"` | Toàn bộ state sau mỗi bước | Debug, xem state tiến hóa |
| `"messages"` | Token LLM + metadata | Chat UI, stream chữ ra màn hình |
| `"custom"` | Dữ liệu tự đẩy qua `get_stream_writer()` | Progress bar trong node |

Async thì dùng `.astream(...)` với cùng bộ mode.

## Subgraph và map-reduce

Subgraph là graph đã compile dùng làm node:

```python
builder.add_node("research", research_graph)   # research_graph = sub_builder.compile()
```

Nếu subgraph dùng **khác schema state**, bọc bằng một hàm dịch state vào/ra —
đừng để hai schema dính nhau ngầm.

Fan-out động (mỗi item một node chạy song song):

```python
from langgraph.types import Send

def fan_out(state):
    return [Send("summarize_one", {"doc": d}) for d in state["documents"]]

builder.add_conditional_edges("split", fan_out, ["summarize_one"])
```

Field nhận kết quả từ các nhánh song song **bắt buộc có reducer** (`add`).

## Cấu hình runtime

```python
graph.invoke(
    inputs,
    {"configurable": {"thread_id": "t1"}, "recursion_limit": 50},
)
```

`recursion_limit` mặc định 25 — graph có vòng lặp retry cần nâng lên, nhưng nâng
`recursion_limit` không thay được cho một điều kiện thoát tử tế.

## Lỗi hay gặp

| Triệu chứng | Nguyên nhân |
|---|---|
| `GraphRecursionError` | Vòng lặp thiếu điều kiện thoát; hoặc conditional edge luôn quay lại |
| `InvalidUpdateError` | Nhiều node ghi cùng field mà field không có reducer |
| Message nhân đôi | Dùng `add` thay vì `add_messages` cho `messages` |
| `interrupt` không dừng | Compile không kèm checkpointer |
| Side effect chạy hai lần | Đặt trước `interrupt()` trong cùng node |
| State mất sau restart | Đang dùng `InMemorySaver` |
| Node không chạy | Quên `add_edge(START, ...)` hoặc quên đăng ký node |

## Trước khi kết thúc task

- Mỗi field trong state đã được quyết định **có reducer hay ghi đè** — có chủ ý,
  không phải ngẫu nhiên.
- Mọi vòng lặp có biến đếm và ngưỡng thoát.
- Checkpointer đúng môi trường (Postgres cho production, không phải InMemory).
- Node không gọi trực tiếp node khác — đi qua edge, nếu không graph mất khả năng
  checkpoint và stream.

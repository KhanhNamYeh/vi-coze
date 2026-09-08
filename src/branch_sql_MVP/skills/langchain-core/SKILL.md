---
name: langchain-core
description: Viết code LangChain — LCEL (prompt | model | parser), chat model, message, prompt template, structured output với Pydantic, định nghĩa tool, và create_agent kèm middleware. Dùng khi task nhắc tới LangChain, LCEL, Runnable, ChatPromptTemplate, with_structured_output, @tool, create_agent, AgentExecutor, hoặc khi đang sửa file có import từ langchain / langchain_core / langchain_openai / langchain_anthropic. KHÔNG dùng cho graph nhiều bước có state — đó là langgraph-workflows.
---

# LangChain core

Viết theo `langchain>=1.0`. **Chạy `uv pip show langchain langchain-core` trước
khi viết** — nếu là 0.x thì import path và `create_agent` đều khác, lúc đó bám
theo code sẵn có trong repo.

## Bản đồ package

| Package | Chứa gì |
|---|---|
| `langchain-core` | `BaseMessage`, `Runnable`, `ChatPromptTemplate`, `@tool`, output parser |
| `langchain` | `create_agent`, `init_chat_model`, middleware |
| `langchain-openai` / `langchain-anthropic` / ... | Binding từng provider |
| `langchain-classic` | Legacy đã tách ra: `LLMChain`, `AgentExecutor`, `RetrievalQA`, `ConversationChain` |

Thấy `LLMChain`, `AgentExecutor`, `initialize_agent`, `RetrievalQA`,
`ConversationBufferMemory` trong code → đó là pattern cũ. Không viết mới theo
chúng; muốn migrate thì nói rõ với user trước, đừng lặng lẽ đổi.

## Khởi tạo model

```python
from langchain.chat_models import init_chat_model

model = init_chat_model("anthropic:claude-sonnet-4-5", temperature=0)
```

`init_chat_model` nhận `"provider:model"` nên đổi provider chỉ sửa một chuỗi.
Cần tham số riêng của provider thì dùng class trực tiếp
(`ChatAnthropic`, `ChatOpenAI`).

> **Cảnh báo tham số sinh văn bản.** Model Anthropic đời mới (Opus 4.7 trở lên,
> Opus 5, Sonnet 5) **từ chối** `temperature`, `top_p`, `top_k` bằng lỗi 400, và
> đã bỏ `budget_tokens` — thay bằng `effort`. Đừng mặc định thêm
> `temperature=0` cho mọi model. Với các model này, điều khiển hành vi bằng
> prompt và `effort`.

## LCEL — nối bằng `|`

```python
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

prompt = ChatPromptTemplate.from_messages([
    ("system", "Bạn là trợ lý pháp lý. Trả lời dựa trên tài liệu được cung cấp."),
    ("human", "{question}"),
])

chain = prompt | model | StrOutputParser()
chain.invoke({"question": "Điều kiện thành lập công ty TNHH?"})
```

Mọi Runnable đều có cùng bộ method — học một lần dùng cho cả chain:

| Method | Dùng khi |
|---|---|
| `.invoke(x)` | Một input, chờ kết quả đầy đủ |
| `.batch([x1, x2])` | Nhiều input song song (có `max_concurrency` trong config) |
| `.stream(x)` | Stream token ra UI |
| `.ainvoke` / `.abatch` / `.astream` | Bản async — dùng trong FastAPI, ingestion nhiều file |

**Ingestion và eval phải dùng `.batch`/`.abatch`.** Vòng `for` gọi `.invoke`
từng cái là lỗi hiệu năng phổ biến nhất khi viết LangChain.

Nhánh song song và biến đổi input:

```python
from langchain_core.runnables import RunnableParallel, RunnablePassthrough

chain = (
    {"context": retriever, "question": RunnablePassthrough()}
    | prompt
    | model
    | StrOutputParser()
)
```

## Message

```python
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
```

`response.content` có thể là `str` **hoặc** list content block (khi có thinking,
citation, ảnh). Đừng giả định là string:

```python
text = response.text() if hasattr(response, "text") else response.content
```

`ToolMessage` phải mang `tool_call_id` khớp với `tool_call["id"]` — thiếu là lỗi
API, không phải lỗi LangChain.

## Structured output

Ưu tiên `.with_structured_output()` hơn parse JSON thủ công:

```python
from pydantic import BaseModel, Field

class Citation(BaseModel):
    source: str = Field(description="Đường dẫn tài liệu gốc")
    quote: str = Field(description="Câu trích nguyên văn")

class Answer(BaseModel):
    text: str
    citations: list[Citation]
    confident: bool = Field(description="False nếu tài liệu không đủ để trả lời")

structured = model.with_structured_output(Answer)
result: Answer = structured.invoke("...")   # đã validate, không cần json.loads
```

Điểm cần biết:
- Mọi `Field(description=...)` đều đi vào schema gửi cho model — mô tả kỹ là
  cách rẻ nhất để tăng độ chính xác.
- `Literal[...]` / `Enum` khóa cứng giá trị hợp lệ, model không bịa được.
- `include_raw=True` trả về cả raw message lẫn parsed — dùng khi cần token usage
  hoặc muốn tự xử lý lỗi parse.
- Provider hỗ trợ strict schema (OpenAI, Anthropic) thì LangChain tự dùng; các
  provider khác rơi về tool-calling — vẫn nên validate ở tầng app.

## Tool

```python
from langchain_core.tools import tool

@tool
def search_documents(query: str, top_k: int = 5) -> str:
    """Tìm trong kho tài liệu nội bộ đã index.

    Gọi tool này khi câu trả lời phụ thuộc vào tài liệu của tổ chức (chính
    sách, hướng dẫn, hợp đồng) thay vì kiến thức chung.

    Args:
        query: Câu truy vấn bằng ngôn ngữ tự nhiên.
        top_k: Số đoạn cần lấy.
    """
    ...
```

Docstring **chính là** description model đọc để quyết định gọi hay không. Viết
rõ *khi nào nên gọi*, không chỉ *tool làm gì* — đây là đòn bẩy lớn nhất lên
chất lượng agent. Cần schema chặt hơn thì `@tool(args_schema=MyModel)`.

Tool cần trả cả nội dung cho model lẫn dữ liệu thô cho code:

```python
@tool(response_format="content_and_artifact")
def retrieve(query: str) -> tuple[str, list[Document]]:
    docs = retriever.invoke(query)
    return "\n\n".join(d.page_content for d in docs), docs
```

## Agent

`create_agent` là ReAct loop dựng sẵn trên LangGraph — dùng khi cần
model-tự-quyết-gọi-tool, không cần tự viết graph:

```python
from langchain.agents import create_agent

agent = create_agent(
    model="anthropic:claude-sonnet-4-5",
    tools=[search_documents, query_database],
    system_prompt="Trả lời dựa trên kết quả tool. Trích dẫn nguồn bằng [số].",
)

result = agent.invoke({"messages": [{"role": "user", "content": "..."}]})
result["messages"][-1].content
```

Agent trả về **state dict**, không phải string — `result["messages"]` là toàn bộ
lịch sử gồm cả tool call.

Middleware để chèn hành vi vào vòng lặp mà không phải viết lại graph:

```python
from langchain.agents.middleware import (
    HumanInTheLoopMiddleware, SummarizationMiddleware,
)

agent = create_agent(
    model=model,
    tools=tools,
    middleware=[
        SummarizationMiddleware(model=model, max_tokens_before_summary=100_000),
        HumanInTheLoopMiddleware(interrupt_on={"delete_records": True}),
    ],
)
```

**Khi nào bỏ `create_agent` để tự viết graph:** cần luồng cố định (không để
model tự chọn đường), cần nhiều node không phải tool, cần rẽ nhánh theo điều
kiện của bạn, hoặc cần state ngoài `messages`. → đọc skill `langgraph-workflows`.

## Streaming

```python
for chunk in chain.stream({"question": "..."}):
    print(chunk, end="", flush=True)
```

Với agent/graph, `.stream()` nhận `stream_mode` (`"values"`, `"updates"`,
`"messages"`) — chi tiết ở skill `langgraph-workflows`.

## Lỗi hay gặp

| Triệu chứng | Nguyên nhân |
|---|---|
| `AttributeError` trên `response.content` | Content là list block, không phải str — dùng `.text()` |
| Chain chạy chậm bất thường | Vòng `for` gọi `.invoke` thay vì `.batch`/`.abatch` |
| Model không gọi tool | Docstring không nói *khi nào* gọi; hoặc thiếu type hint nên schema rỗng |
| 400 từ Anthropic | Truyền `temperature`/`top_p`/`budget_tokens` cho model đời mới |
| `ImportError` sau nâng version | Symbol đã dời sang `langchain-classic` hoặc `langchain-core` |
| Prompt cache không ăn | Có timestamp/UUID trong system prompt, hoặc danh sách tool đổi giữa phiên |

## Trước khi kết thúc task

- Không để lẫn `AgentExecutor` (cũ) với `create_agent` (mới) trong cùng một flow.
- Mọi lệnh gọi model đi qua một chỗ khởi tạo chung, không rải `init_chat_model`
  khắp file.
- API key đọc từ env, không hardcode, không commit `.env`.

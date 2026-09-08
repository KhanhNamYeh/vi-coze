---
name: agent-memory
description: Quản lý bộ nhớ và ngữ cảnh cho agent — phân biệt checkpointer với store, cắt tỉa và tóm tắt lịch sử message, long-term memory qua nhiều session, semantic/episodic/procedural memory, và context engineering để không tràn context window. Dùng khi task nhắc tới memory, ghi nhớ, lịch sử hội thoại, context window đầy, tóm tắt hội thoại, trim_messages, BaseStore, hoặc khi agent quên thông tin giữa các session.
---

# Agent memory & context engineering

**Chạy `uv pip show langgraph langchain-core` trước khi viết.**

## Phân biệt hai thứ hay bị lẫn

| | Checkpointer | Store |
|---|---|---|
| Lưu gì | Toàn bộ state của graph tại mỗi bước | Dữ liệu do bạn chủ động ghi |
| Phạm vi | Một `thread_id` (một cuộc hội thoại) | Xuyên thread, xuyên session |
| Mục đích | Resume, replay, HITL, chống crash | "Agent nhớ user thích gì" |
| API | `compile(checkpointer=...)` | `store.put()` / `store.search()` |

Checkpointer **không phải** long-term memory. Cùng `thread_id` thì agent nhớ;
đổi `thread_id` là mất sạch. Muốn agent nhớ user qua các cuộc hội thoại khác
nhau thì phải có Store — hai cơ chế độc lập, thường dùng cùng lúc.

## Short-term: lịch sử trong một thread

Vấn đề duy nhất: **lịch sử chỉ có tăng**. Agent chạy 30 lượt tool là context
phình ra, chi phí mỗi lượt tăng theo, rồi tràn.

Ba cách xử lý, dùng kết hợp:

### 1. Cắt tỉa (rẻ nhất, mất thông tin)

```python
from langchain_core.messages import trim_messages

def agent_node(state):
    msgs = trim_messages(
        state["messages"],
        max_tokens=60_000,
        strategy="last",              # giữ phần cuối
        token_counter=llm,
        include_system=True,          # giữ system prompt
        start_on="human",             # bắt đầu ở lượt human, không cắt giữa cặp tool
        allow_partial=False,
    )
    return {"messages": [llm.invoke(msgs)]}
```

**`start_on="human"` là bắt buộc.** Cắt bừa có thể để lại `ToolMessage` mồ côi
không có `AIMessage` chứa `tool_call` tương ứng → API trả 400. Đây là lỗi phổ
biến nhất khi tự viết logic cắt lịch sử.

### 2. Tóm tắt (giữ thông tin, tốn một lượt gọi model)

Khi vượt ngưỡng, gọi model tóm tắt phần cũ rồi thay bằng một message duy nhất:

```python
from langchain_core.messages import RemoveMessage, SystemMessage

def summarize(state):
    if count_tokens(state["messages"]) < 80_000:
        return {}
    old, keep = state["messages"][:-6], state["messages"][-6:]
    summary = llm.invoke(
        [SystemMessage("Tóm tắt hội thoại dưới đây. Giữ nguyên: quyết định đã "
                       "chốt, dữ kiện đã xác minh, việc còn dang dở. Bỏ: lời "
                       "chào hỏi, tool call đã hoàn tất không còn liên quan.")]
        + old
    )
    return {"messages": [RemoveMessage(id=m.id) for m in old]
                        + [SystemMessage(f"Tóm tắt phần trước:\n{summary.content}")]}
```

`RemoveMessage` chỉ hoạt động với reducer `add_messages` — dùng `add` thường thì
không xóa được gì.

Chất lượng tóm tắt nằm ở prompt: **nói rõ giữ gì, bỏ gì**. "Tóm tắt hội thoại"
chung chung sẽ mất đúng thứ agent cần (id, đường dẫn, quyết định).

### 3. Đẩy ra ngoài context (tốt nhất cho dữ liệu lớn)

Tool trả về 200KB JSON thì đừng nhét cả vào context. Ghi ra file / store, trả
về model một bản tóm tắt kèm handle để đọc lại khi cần:

```python
@tool(response_format="content_and_artifact")
def query_database(sql: str) -> tuple[str, list]:
    rows = run(sql)
    preview = f"{len(rows)} dòng. 5 dòng đầu:\n{format(rows[:5])}"
    return preview, rows          # model thấy preview, code giữ rows
```

Đây là đòn bẩy lớn nhất về chi phí trong agent có tool nặng dữ liệu, lớn hơn cả
tóm tắt.

## Long-term: nhớ qua nhiều session

```python
from langgraph.store.memory import InMemoryStore     # dev
# from langgraph.store.postgres import PostgresStore # production

store = InMemoryStore()
graph = builder.compile(checkpointer=checkpointer, store=store)
```

Node nhận store qua tham số có tên:

```python
from langgraph.store.base import BaseStore

def agent_node(state, *, store: BaseStore, config):
    user_id = config["configurable"]["user_id"]
    ns = ("memories", user_id)

    recalled = store.search(ns, query=state["messages"][-1].content, limit=3)
    context = "\n".join(m.value["text"] for m in recalled)

    reply = llm.invoke([SystemMessage(f"Đã biết về người dùng:\n{context}")] + state["messages"])
    return {"messages": [reply]}
```

Namespace là tuple — dùng để cô lập dữ liệu: `("memories", user_id)` khác
`("memories", user_id_khac)`. **Cô lập theo user là bắt buộc**, không phải tùy
chọn; store dùng chung giữa user là rò rỉ dữ liệu.

Muốn `search(query=...)` tìm theo ngữ nghĩa thì store phải được cấu hình
embedding (`index={"embed": embeddings, "dims": 768}`), nếu không nó chỉ lọc
theo namespace/prefix.

## Ba loại memory và cách lưu khác nhau

| Loại | Là gì | Lưu thế nào | Ghi khi nào |
|---|---|---|---|
| **Semantic** | Sự kiện về user/thế giới ("Minh dùng Postgres") | Store, mỗi fact một record | Khi phát hiện thông tin mới đáng nhớ |
| **Episodic** | Chuyện đã xảy ra ("lần trước fix bug X bằng cách Y") | Store, mỗi phiên một record kèm kết quả | Cuối phiên |
| **Procedural** | Cách làm việc ("user thích trả lời ngắn") | Ghi vào system prompt / file instruction | Khi user sửa lưng agent |

Đừng nhồi cả ba vào một namespace rồi `search` chung — chúng được dùng ở những
thời điểm khác nhau trong prompt.

**Hai chiến lược ghi:**

- *Trong luồng* (hot path): agent tự gọi tool `save_memory` khi thấy đáng nhớ.
  Đơn giản, nhưng thêm latency và agent hay quên gọi.
- *Ngoài luồng* (background): sau phiên, một job đọc transcript và rút ra
  memory. Không ảnh hưởng latency, chất lượng tốt hơn, nhưng phức tạp hơn.

Bắt đầu bằng cách trong luồng, chuyển sang ngoài luồng khi latency thành vấn đề.

## Context engineering — quyết định đưa gì vào

Đưa **đúng** thông tin quan trọng hơn đưa **nhiều**. Bốn nguyên tắc:

1. **Đúng vị trí.** Model nhớ đầu và cuối rõ hơn giữa. Chỉ thị quan trọng nhất
   đặt ở system prompt (đầu) hoặc ngay trước câu hỏi (cuối), không giấu ở giữa
   một đống tài liệu.
2. **Có nhãn.** Tài liệu chèn vào phải bọc thẻ và ghi nguồn
   (`<document source="...">`), nếu không model không phân biệt được đâu là dữ
   liệu, đâu là chỉ thị của bạn.
3. **Ổn định trước, biến động sau.** Vì prompt cache — phần đổi mỗi lượt đặt
   cuối cùng.
4. **Có ngân sách.** Đặt hạn mức token cho từng phần (system / memory / tài liệu
   / lịch sử) và cưỡng chế nó. Không có ngân sách thì phần nào cũng phình.

> **Cẩn thận khi hiển thị ngân sách còn lại cho model.** Nếu system prompt ghi
> "còn 5000 token", model có xu hướng vội vàng kết thúc sớm. Cắt ở tầng code,
> đừng kể cho model nghe.

## Lỗi hay gặp

| Triệu chứng | Nguyên nhân |
|---|---|
| API trả 400 sau khi trim | Cắt để lại `ToolMessage` mồ côi — thiếu `start_on="human"` |
| `RemoveMessage` không xóa được | State dùng reducer `add` thay vì `add_messages` |
| Agent quên khi đổi session | Nhầm checkpointer là long-term memory — cần Store |
| Memory user này lẫn user kia | Namespace không tách theo `user_id` |
| `store.search(query=...)` trả về vô nghĩa | Store chưa cấu hình embedding index |
| Chi phí tăng dần theo số lượt | Không có trim/summarize, lịch sử chỉ tăng |
| Tóm tắt xong agent mất dấu việc đang làm | Prompt tóm tắt không chỉ định giữ "việc còn dang dở" |
| Mất hết state khi restart | `InMemorySaver`/`InMemoryStore` trong production |

## Trước khi kết thúc task

- Checkpointer và Store là hai quyết định riêng — đã chọn đúng cái cho đúng nhu cầu.
- Có cơ chế chặn lịch sử phình vô hạn (trim hoặc summarize), có ngưỡng cụ thể.
- Namespace của Store tách theo user/tenant.
- Production dùng `PostgresSaver`/`PostgresStore`, không phải bản in-memory.
- Dữ liệu tool lớn đi qua artifact, không đổ thẳng vào context.

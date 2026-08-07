---
name: agent-production
description: Đưa agent lên production — đánh giá trajectory (chuỗi hành động) chứ không chỉ output cuối, observability, kiểm soát chi phí bằng caching và model routing, deploy và durable execution, rate limit, và bảo mật (prompt injection, secret, egress). Dùng khi task nhắc tới deploy agent, chi phí agent, agent chậm, trajectory eval, tool-call accuracy, prompt injection, hoặc chuẩn bị đưa agent ra thật.
---

# Agent trên production

Skill này nối tiếp `langsmith-eval` (eval RAG/output) — ở đây là những thứ chỉ
xuất hiện khi agent chạy thật.

## Eval agent: output đúng chưa đủ

Agent trả lời đúng nhờ đi đường vòng 12 bước vẫn là agent hỏng — đắt, chậm, và
sẽ sai ở input hơi khác. Phải đo cả **trajectory**.

| Chiều đo | Câu hỏi | Cách đo |
|---|---|---|
| **Kết quả cuối** | Câu trả lời đúng không? | So với đáp án chuẩn, hoặc LLM-as-judge |
| **Chọn tool** | Có gọi đúng tool cần thiết không? | So tập tool đã gọi với tập kỳ vọng |
| **Hiệu quả** | Bao nhiêu bước / token so với đường tối ưu? | Đếm bước, cộng `usage_metadata` |
| **Phục hồi lỗi** | Tool lỗi thì có xoay được không? | Test có tiêm lỗi chủ động |
| **An toàn** | Có gọi tool nguy hiểm khi không nên? | Assert cứng: tool cấm không được xuất hiện |

```python
def trajectory_metrics(result, expected_tools: set[str]) -> dict:
    called = [
        c["name"]
        for m in result["messages"]
        for c in (getattr(m, "tool_calls", None) or [])
    ]
    return {
        "tool_recall": len(expected_tools & set(called)) / max(len(expected_tools), 1),
        "steps": len(called),
        "repeated": len(called) - len(set(called)),   # >0 là dấu hiệu lặp
    }
```

**Đo tập tool, đừng đo thứ tự chính xác.** Có nhiều đường đi hợp lệ tới cùng
một kết quả; ép đúng một trình tự là biến eval thành test giòn, đỏ mỗi lần model
đổi cách làm dù kết quả vẫn tốt.

Loại test không thể thiếu — **tiêm lỗi**:

```python
def test_agent_recovers_when_search_fails():
    with patch_tool("search_documents", side_effect="LỖI: dịch vụ tạm ngưng"):
        result = agent.invoke({"messages": [("user", "Chính sách nghỉ phép?")]})
    assert result["messages"][-1].content            # vẫn trả lời được điều gì đó
    assert "LỖI" not in result["messages"][-1].content  # không xả lỗi thô ra user
```

Và một test an toàn cho mỗi tool nguy hiểm: input cố tình dụ agent gọi nó, assert
nó **không** được gọi khi chưa duyệt.

## Observability

```bash
export LANGSMITH_TRACING=true
export LANGSMITH_PROJECT=vi-coze-prod      # tách khỏi dev
```

Ba thứ phải nhìn thấy được trên mỗi phiên, nếu không thì không debug được
production: **số bước**, **token mỗi lượt**, và **tool nào lỗi**.

```python
result = agent.invoke(inputs, config={
    "configurable": {"thread_id": session_id},
    "metadata": {"user_id": user_id, "agent_version": "v3", "model": "sonnet-4-5"},
    "tags": ["prod"],
    "recursion_limit": 20,
})
```

`agent_version` trong metadata cho phép so sánh hai phiên bản trên dữ liệu thật
— thứ mà eval offline không thay thế được.

Cảnh báo nên đặt: tỉ lệ chạm `recursion_limit`, tỉ lệ tool lỗi, token trung bình
mỗi phiên (tăng đột ngột = lịch sử không được cắt), tỉ lệ phiên cần người can thiệp.

## Chi phí

Chi phí agent tăng **theo bình phương** số lượt, vì mỗi lượt gửi lại toàn bộ
lịch sử. Ba đòn bẩy, theo thứ tự hiệu quả:

### 1. Prompt caching — làm trước tiên

Bố cục prompt: **tĩnh trước, động sau**. Tool schema và system prompt ổn định
nằm đầu; task và thời gian nằm cuối. Ba thứ giết cache:

- Timestamp / UUID trong system prompt.
- Đổi danh sách tool giữa phiên.
- Đổi model giữa phiên (cache theo từng model).

Kiểm chứng bằng số thật, không phải bằng niềm tin — `cache_read_input_tokens`
bằng 0 qua nhiều lượt nghĩa là cache không ăn.

### 2. Cắt lịch sử

Xem `agent-memory`. Không có trim/summarize thì chi phí mỗi lượt chỉ có tăng.

### 3. Model routing

Không phải bước nào cũng cần model mạnh nhất:

| Bước | Model |
|---|---|
| Phân loại intent, routing, chấm điểm | Model nhỏ |
| Vòng lặp reasoning chính | Model mạnh |
| Tóm tắt, trích xuất, format | Model nhỏ |

Bù trừ: đổi model là mất cache của phần đó. Đáng đổi khi bước phụ chạy nhiều
lần hoặc prompt của nó ngắn.

**Đo trước khi tối ưu.** Cộng `usage_metadata` theo từng node trong một phiên
thật; thường 80% chi phí nằm ở một node duy nhất, tối ưu chỗ khác là phí công.

## Deploy

| Cách | Phù hợp | Đánh đổi |
|---|---|---|
| Bọc trong FastAPI, tự chạy | Đã có hạ tầng, muốn kiểm soát hoàn toàn | Tự lo checkpointer, queue, retry, scaling |
| LangGraph Platform / Server | Muốn có sẵn persistence, streaming, HITL API | Phụ thuộc nền tảng |

Tự bọc thì bốn thứ này bắt buộc phải có:

1. **Checkpointer bền vững** — `PostgresSaver`, không phải `InMemorySaver`.
   Nhớ gọi `.setup()` một lần để tạo bảng.
2. **`thread_id` gắn với user/session thật**, không sinh ngẫu nhiên mỗi request
   (mất hết ngữ cảnh).
3. **Chạy nền cho task dài** — agent chạy vài phút thì đừng giữ HTTP request;
   trả job id, stream qua SSE/WebSocket.
4. **Timeout và `recursion_limit`** ở mọi entrypoint.

Endpoint tối thiểu:

```python
@app.post("/chat")
async def chat(req: ChatRequest):
    config = {
        "configurable": {"thread_id": req.session_id},
        "recursion_limit": 20,
    }
    async def gen():
        async for mode, chunk in agent.astream(
            {"messages": [("user", req.message)]}, config, stream_mode=["updates", "messages"]
        ):
            yield sse(mode, chunk)
    return StreamingResponse(gen(), media_type="text/event-stream")
```

**Stream là bắt buộc với agent**, không phải tính năng thêm. Agent chạy 30 giây
mà im lặng thì người dùng tưởng treo — tối thiểu phải báo "đang tìm kiếm…" qua
`stream_mode="updates"`.

### Durable execution

Có checkpointer thì agent chết giữa chừng vẫn chạy tiếp được từ node dở dang:

```python
try:
    result = agent.invoke(inputs, config)
except Exception:
    result = agent.invoke(None, config)      # tiếp từ checkpoint gần nhất
```

Điều kiện: **node phải idempotent**. Node gửi email rồi crash trước khi ghi
checkpoint sẽ gửi email lần hai khi resume. Việc có side effect nên tách thành
node riêng, nhỏ nhất có thể.

## Rate limit và lỗi tạm thời

Backoff theo cấp số nhân kèm jitter, ưu tiên header `Retry-After` nếu provider
trả về. Đa số SDK đã tự retry — kiểm tra `max_retries` trước khi tự viết thêm
một lớp nữa (hai lớp retry lồng nhau làm thời gian chờ nhân lên).

> **Không luân phiên nhiều API key để vượt rate limit.** Nhiều key cho một tổ
> chức thường vi phạm điều khoản dịch vụ, và khi bị khóa thì khóa cả tài khoản.
> Đường đi đúng: `Retry-After` → backoff → xin nâng tier → Batch API cho phần
> không cần realtime.

## Bảo mật

| Rủi ro | Phòng thủ |
|---|---|
| Prompt injection qua tool output | Bọc nhãn untrusted; người duyệt cho hành động khó hoàn tác; giới hạn quyền của agent (xem `agent-tools-mcp`) |
| Secret rò ra ngoài | Không đặt secret trong system prompt; inject ở tầng code khi gọi API; redact trước khi ghi log/trace |
| Agent gọi API ngoài ý muốn | Allowlist domain, chặn egress ở tầng hạ tầng |
| Dữ liệu user lẫn nhau | `thread_id` và namespace của Store tách theo user — kiểm bằng test |
| Trace chứa PII | Bật redaction; xem lại field nào đang được gửi lên nền tảng trace |

Nguyên tắc bao trùm: **thiết kế sao cho model bị lừa cũng không gây hại được**.
Mọi phòng thủ đặt ở tầng prompt đều có thể bị ghi đè bởi chính prompt injection.

## Checklist trước khi lên production

- [ ] `recursion_limit` và timeout ở mọi entrypoint
- [ ] Checkpointer là Postgres (đã `.setup()`), không phải in-memory
- [ ] Có cắt/tóm tắt lịch sử, đã đo token trung bình mỗi phiên
- [ ] Prompt cache đang thật sự ăn (`cache_read_input_tokens` > 0)
- [ ] Stream tiến độ ra client
- [ ] Tracing bật, project tách riêng prod/dev, có metadata `agent_version`
- [ ] Có test tiêm lỗi tool và test an toàn cho từng tool nguy hiểm
- [ ] Tool output từ nguồn ngoài được bọc nhãn untrusted
- [ ] Không có secret trong system prompt; log đã redact
- [ ] Node có side effect là idempotent hoặc tách riêng
- [ ] Cảnh báo: tỉ lệ chạm recursion_limit, tỉ lệ tool lỗi, token/phiên

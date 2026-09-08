---
name: agent-design
description: Quyết định kiến trúc agent trước khi viết code — có nên dùng agent không, chọn paradigm (reflex/planning/ReAct), lắp ráp system prompt, chiến lược dừng vòng lặp, tách plan/act, xử lý lỗi tool và phát hiện agent bị kẹt. Dùng khi task nhắc tới thiết kế agent, ReAct, planning agent, system prompt cho agent, agent lặp vô hạn, recursion_limit, agent gọi sai tool, hoặc khi review một agent đã có.
---

# Thiết kế agent

Skill này là tầng **quyết định**, không phải tầng cú pháp. Cú pháp LangGraph ở
`langgraph-workflows`; cú pháp LangChain ở `langchain-core`.

## Câu hỏi đầu tiên: có cần agent không?

Ranh giới duy nhất giữa pipeline và agent: **ai quyết định bước tiếp theo** —
code bạn viết, hay model.

| Bài toán | Dùng |
|---|---|
| Input → output, luồng biết trước | Pipeline / LCEL. **Không phải agent** |
| Retrieve → generate cố định | RAG pipeline |
| Model tự chọn tool, số bước không biết trước | Agent |
| Nhiều bước phụ thuộc kết quả trung gian, cần quan sát rồi điều chỉnh | Agent (ReAct) |

Cái giá của agent là thật: latency cao hơn (nhiều lượt gọi model), chi phí cao
hơn (lịch sử gửi lại mỗi lượt), và debug khó hơn nhiều. **Nếu luồng cố định giải
được thì đừng dùng agent** — đây là lỗi kiến trúc phổ biến nhất, không phải lỗi
code.

Dấu hiệu agent bị dùng sai chỗ: trace luôn cho ra đúng một chuỗi tool giống
nhau, không lần nào rẽ khác. Đó là pipeline đang trả tiền cho quyền tự quyết mà
nó không dùng tới.

## Chọn paradigm

| Paradigm | Lập kế hoạch | Phù hợp | Điểm yếu |
|---|---|---|---|
| **Reflex** | Không | Một bước, map input → action | Không xử lý được task nhiều bước |
| **Planning** | Toàn bộ trước khi chạy | Biết trước cấu trúc task, các bước độc lập | Kế hoạch sai từ đầu thì sai cả chuỗi |
| **ReAct** | Từng bước theo quan sát | Không biết trước cần mấy bước; bước sau phụ thuộc kết quả bước trước | Dễ lạc, dễ lặp nếu không có điều kiện dừng |

**Mặc định là ReAct.** Chỉ chuyển sang Planning khi task đủ lớn để hưởng lợi từ
việc nhìn toàn cảnh trước (research nhiều nguồn, refactor nhiều file), và khi
đó vẫn giữ ReAct **bên trong** từng bước của kế hoạch.

Kết hợp thực chiến: `plan → [ReAct cho từng bước] → tổng hợp`. Kế hoạch cho
hướng đi, ReAct xử lý cái bất ngờ.

## Lắp ráp system prompt

Đừng viết một khối văn dài. Ráp từ các phần rồi lọc theo task:

| Tầng | Trả lời | Tĩnh hay động? |
|---|---|---|
| Identity | Agent là ai | Tĩnh |
| Constraints | Tuyệt đối không làm gì | Tĩnh — đặt sớm, đặt rõ |
| Capabilities | Có tool gì | Lọc theo task |
| Context | Môi trường lúc này (thư mục, thời gian, user) | Động |
| Behavior | Tone, độ dài, phong cách quyết định | Tĩnh |
| Knowledge | Skill/memory liên quan | Nạp theo nhu cầu |

**Thứ tự quan trọng vì prompt cache.** Phần tĩnh (identity, constraints,
behavior) đặt **trước**, phần động (thời gian, user, task) đặt **sau**. Nhét
timestamp vào đầu system prompt là vô hiệu hóa cache của toàn bộ phần sau —
mỗi lượt trả tiền full giá.

Cùng lý do: **không đổi danh sách tool giữa phiên**. Tool render ở vị trí 0;
thêm/bớt một tool là mất sạch cache.

Constraint viết ở dạng khẳng định + lý do, không phải danh sách cấm dài:

```
Xác nhận với người dùng trước khi chạy lệnh thay đổi trạng thái hệ thống
(xóa, restart, sửa config) — những việc này khó hoàn tác.
```

hơn là `TUYỆT ĐỐI KHÔNG BAO GIỜ xóa file. KHÔNG restart. KHÔNG...`. Model đời
mới bám system prompt rất sát; viết to và gay gắt gây over-trigger, agent hỏi
xin phép cả những việc vô hại.

## Dừng vòng lặp — luôn có ít nhất hai lớp

| Chiến lược | Cách làm | Vai trò |
|---|---|---|
| Model tự dừng | Không gọi tool nữa | Cơ chế chính |
| Max steps | `recursion_limit` khi invoke | **Lưới an toàn, luôn có** |
| Stop tool tường minh | Bắt gọi `final_answer(...)` mới xong | Task cần xác nhận rõ đã hoàn thành |
| Kiểm tra mục tiêu | Một lượt gọi model riêng hỏi "đã đạt chưa" | Task quan trọng, chấp nhận tốn thêm |
| Ngân sách token | Đếm và cắt khi vượt | Production |

`recursion_limit` mặc định 25 — không thay được cho điều kiện dừng tử tế, nó chỉ
là cầu chì. Agent chạm limit là **triệu chứng**, phải đi tìm nguyên nhân chứ
đừng nâng số lên rồi bỏ qua.

Stop tool tường minh giải quyết bài toán "agent nói đã xong nhưng chưa làm gì":

```python
@tool
def final_answer(answer: str) -> str:
    """Nộp kết quả cuối. CHỈ gọi khi đã hoàn thành toàn bộ nhiệm vụ."""
    return answer
```

## Lỗi tool: trả về cho model, đừng giấu

Tool hỏng phải thành **một quan sát bình thường**, không phải exception làm sập
graph:

```python
try:
    output = execute(call)
except Exception as e:
    output = f"LỖI: {e}. Hãy thử cách tiếp cận khác."
```

Ba kiểu che giấu lỗi đều làm agent tệ đi:
- Retry âm thầm → model không biết nó đang đi sai đường.
- Trả giá trị mặc định → model tưởng thành công, xây tiếp trên dữ liệu rác.
- Raise ra ngoài → mất toàn bộ tiến độ đã làm.

Thông báo lỗi nên nói **làm gì tiếp**, không chỉ *cái gì hỏng*:
`"File không tồn tại. Dùng list_directory để xem tên file có sẵn."`

## Phát hiện agent bị kẹt

`recursion_limit` cắt ngang âm thầm; phát hiện lặp thì can thiệp được sớm hơn.

```python
def is_stuck(state, window: int = 3) -> bool:
    calls = [
        str(m.tool_calls[0])
        for m in state["messages"][-window * 2:]
        if getattr(m, "tool_calls", None)          # LUÔN dùng getattr
    ]
    return len(calls) >= window and len(set(calls)) == 1
```

Kẹt rồi thì **đổi thông tin đầu vào**, đừng chỉ bảo "thử cách khác": chèn một
system message liệt kê những gì đã thử và vì sao thất bại. Model lặp thường vì
context không cho nó biết là nó đang lặp.

> **`getattr(m, "tool_calls", None)`, không phải `m.tool_calls`.** Message cuối
> có thể là `ToolMessage` hoặc `HumanMessage` — truy cập thẳng là `AttributeError`.
> Đây là lỗi runtime phổ biến nhất khi viết agent bằng LangGraph.

## Tách plan / act

Agent lao vào sửa trước khi hiểu là lỗi kinh điển. Cách chữa **không phải** dặn
trong prompt ("hãy lập kế hoạch trước") — model vẫn lẫn lộn. Cách chữa là
**giới hạn tool theo node**:

| Phase | Tool được bind |
|---|---|
| Plan | Chỉ read-only: `read_file`, `search`, `list_dir` |
| Act | Toàn bộ, sau khi kế hoạch được duyệt |

```python
plan_llm = llm.bind_tools(READ_ONLY_TOOLS)
act_llm  = llm.bind_tools(ALL_TOOLS)
```

Ranh giới cứng ở tầng code, không phải lời khuyên ở tầng prompt. Chèn
`interrupt()` giữa hai phase để người duyệt kế hoạch (xem `langgraph-workflows`).

## Checklist review một agent

- [ ] Trace có thực sự rẽ nhánh khác nhau không, hay luôn một đường? (nếu luôn
      một đường → nên là pipeline)
- [ ] Có `recursion_limit` **và** một điều kiện dừng thật?
- [ ] Mọi truy cập `tool_calls` đều qua `getattr`?
- [ ] Lỗi tool quay về model dưới dạng ToolMessage, không phải exception?
- [ ] System prompt: phần tĩnh trước, phần động sau? Tool list cố định suốt phiên?
- [ ] Tool có side effect có đi qua bước xác nhận?
- [ ] Constraint viết ở dạng khẳng định có lý do, không phải danh sách cấm viết hoa?

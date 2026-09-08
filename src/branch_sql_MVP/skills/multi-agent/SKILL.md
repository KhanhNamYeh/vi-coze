---
name: multi-agent
description: Thiết kế hệ nhiều agent phối hợp — quyết định có thực sự cần multi-agent không, chọn pattern (supervisor, handoff/swarm, hierarchical), chia state giữa các agent, chuyển giao bằng Command, cô lập context, và kiểm soát chi phí. Dùng khi task nhắc tới multi-agent, supervisor, handoff, swarm, sub-agent, agent phối hợp, orchestrator, hoặc khi một agent đang quá tải vì có quá nhiều tool.
---

# Multi-agent systems

**Chạy `uv pip show langgraph` trước khi viết.**

## Trước tiên: gần như chắc chắn bạn chưa cần multi-agent

Mỗi agent thêm vào phải **dựng lại ngữ cảnh từ đầu**, làm việc, rồi báo cáo về —
và orchestrator lại phải đọc báo cáo đó. Chi phí token thường nhân 3–5 lần,
latency cộng dồn tuần tự, và debug khó hơn hẳn vì lỗi có thể nằm ở khâu chuyển
giao chứ không ở agent nào.

Thử theo thứ tự này trước khi thêm agent:

| Triệu chứng | Cách rẻ hơn multi-agent |
|---|---|
| Quá nhiều tool, agent chọn nhầm | Sửa description ("KHÔNG dùng cho..."), gộp tool, lọc toolset theo task |
| Prompt quá dài, agent lẫn lộn nhiệm vụ | Tách thành các **node** trong một graph, mỗi node bind tool riêng |
| Context tràn | Trim/summarize, đẩy dữ liệu lớn ra artifact |
| Cần bước chuyên biệt (dịch, tóm tắt, chấm điểm) | Một lượt gọi LLM trong một node, không cần agent đầy đủ |

**Multi-agent chỉ thật sự đáng khi:** các nhánh công việc **độc lập và chạy song
song được**, hoặc mỗi nhánh cần **model/toolset/prompt khác nhau đủ nhiều** để
không nhồi chung được, hoặc cần cô lập context (agent A không được thấy dữ liệu
của agent B).

Kiểm tra ngược: nếu các "agent" của bạn luôn chạy tuần tự theo đúng một thứ tự,
đó là **pipeline nhiều node**, không phải multi-agent — dựng bằng graph thường,
rẻ hơn nhiều.

## Chọn pattern

| Pattern | Cấu trúc | Dùng khi | Đánh đổi |
|---|---|---|---|
| **Supervisor** | Một điều phối viên gọi các worker, worker luôn báo cáo về | Mặc định. Cần kiểm soát và quan sát rõ | Supervisor là nút cổ chai, tốn thêm một lượt gọi mỗi lần chuyển |
| **Handoff / swarm** | Agent tự chuyển quyền cho agent khác, không qua trung gian | Hội thoại chuyển giữa các chuyên môn (bán hàng → kỹ thuật) | Khó đoán luồng, dễ chuyền qua chuyền lại |
| **Hierarchical** | Supervisor của các supervisor | Hệ rất lớn, nhiều nhóm chuyên môn | Phức tạp; hiếm khi thật sự cần |
| **Parallel fan-out** | Chia việc → chạy song song → gộp | Nhiều nhánh độc lập (nghiên cứu 5 nguồn) | **Bắt buộc reducer**; phải xử lý nhánh lỗi |

**Bắt đầu bằng supervisor.** Nó dễ debug nhất và chuyển sang pattern khác sau
không tốn kém.

## Supervisor

```python
from typing import Annotated, Literal, TypedDict
from operator import add
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.types import Command

class TeamState(TypedDict):
    messages: Annotated[list, add_messages]
    findings: Annotated[list[str], add]      # nhiều agent ghi -> PHẢI có reducer
    next_agent: str

def supervisor(state: TeamState) -> Command[Literal["researcher", "writer", "__end__"]]:
    decision = router_llm.with_structured_output(Route).invoke(
        [SystemMessage(SUPERVISOR_PROMPT)] + state["messages"]
    )
    return Command(goto=decision.next, update={"next_agent": decision.next})

def researcher(state: TeamState) -> Command[Literal["supervisor"]]:
    result = research_agent.invoke({"messages": state["messages"][-1:]})   # cô lập
    return Command(
        goto="supervisor",
        update={"findings": [summarize(result)]},      # trả về TÓM TẮT, không phải toàn bộ
    )
```

Hai điểm quyết định chất lượng, đều nằm ở worker chứ không ở supervisor:

1. **Truyền vào cái gì.** `state["messages"][-1:]` chứ không phải toàn bộ lịch
   sử — worker chỉ cần nhiệm vụ của nó. Truyền hết là nhân đôi chi phí và làm
   worker phân tâm.
2. **Trả về cái gì.** Trả bản tóm tắt, không phải toàn bộ transcript nội bộ của
   worker. Supervisor không cần đọc 30 tool call của researcher.

## Chia state — nơi hỏng nhiều nhất

Đây là lỗi số một khi lên multi-agent:

```python
class BadState(TypedDict):
    results: list[str]          # 3 agent chạy song song cùng ghi -> InvalidUpdateError

class GoodState(TypedDict):
    results: Annotated[list[str], add]     # nối thêm, an toàn khi fan-out
```

Quy tắc: **field nào có từ hai node trở lên ghi vào thì phải có reducer.**
Không có `Annotated` nghĩa là "ghi đè" — chạy tuần tự thì im lặng mất dữ liệu,
chạy song song thì `InvalidUpdateError`.

Ba tầng chia sẻ, chọn có chủ ý:

| Tầng | Ai thấy | Dùng cho |
|---|---|---|
| Private trong agent | Chỉ agent đó | Suy nghĩ trung gian, tool call nội bộ |
| Shared state | Mọi node trong graph | Kết quả đã tóm tắt, cờ điều khiển |
| Store | Xuyên thread, xuyên session | Memory dài hạn (xem `agent-memory`) |

Mặc định nên là **private**, chỉ đẩy lên shared cái thật sự cần chia sẻ. Đổ hết
mọi thứ vào `messages` chung là cách nhanh nhất để nổ context.

## Fan-out song song

```python
from langgraph.types import Send

def dispatch(state):
    return [Send("research_one", {"topic": t}) for t in state["subtopics"]]

builder.add_conditional_edges("plan", dispatch, ["research_one"])
```

Ba thứ phải có khi fan-out:
- Reducer trên mọi field nhận kết quả.
- Xử lý nhánh lỗi — một nhánh hỏng không được làm sập cả mẻ; trả về marker lỗi
  để bước gộp biết mà bỏ qua.
- Giới hạn số nhánh. `Send` cho 200 subtopic là 200 lượt gọi model song song —
  chặn ở tầng code, đừng để model quyết.

## Handoff

Agent tự chuyển quyền, không qua supervisor:

```python
@tool
def transfer_to_technical(reason: str) -> str:
    """Chuyển sang bộ phận kỹ thuật khi câu hỏi vượt phạm vi bán hàng."""
    return f"Đã chuyển: {reason}"

def sales_agent(state) -> Command:
    reply = sales_llm.invoke(state["messages"])
    if called(reply, "transfer_to_technical"):
        return Command(goto="technical", update={"messages": [reply]})
    return Command(goto=END, update={"messages": [reply]})
```

Handoff dễ rơi vào vòng chuyền qua chuyền lại. Luôn đếm số lần chuyển và cắt ở
một ngưỡng, với đường thoát về người thật.

## Chi phí — tính trước khi xây

Ước lượng thô cho một task:

```
tokens ≈ Σ_agent (system_prompt + context_truyền_vào + lịch_sử_nội_bộ)
       + orchestrator_đọc_lại_mọi_báo_cáo
```

Thực tế: supervisor + 3 worker thường tốn **3–5 lần** một agent đơn cho cùng
task. Ba cách giảm, theo thứ tự hiệu quả:

1. Worker trả **tóm tắt**, không trả transcript.
2. Truyền vào worker đúng nhiệm vụ, không truyền cả lịch sử.
3. Worker đơn giản dùng model rẻ hơn — nhưng lưu ý cache là theo model, đổi
   model giữa chừng là mất cache của phần đó.

Đo bằng token thật (`usage_metadata` trên mỗi trace) trước và sau khi tách
agent. Nếu multi-agent không cải thiện chất lượng đủ để bù 3–5 lần chi phí,
quay lại một agent.

## Lỗi hay gặp

| Triệu chứng | Nguyên nhân |
|---|---|
| `InvalidUpdateError` | Field bị nhiều node ghi mà không có reducer |
| Chi phí gấp nhiều lần dự tính | Worker nhận cả lịch sử; hoặc trả nguyên transcript về |
| Agent chuyền qua chuyền lại không dứt | Handoff không đếm số lần chuyển |
| Supervisor gọi sai worker | Mô tả năng lực worker mơ hồ — viết như tool description, có "không dùng cho" |
| Kết quả song song thiếu | Nhánh lỗi làm hỏng bước gộp; hoặc reducer ghi đè thay vì nối |
| Debug không biết lỗi ở đâu | Không tách trace theo agent — xem `langsmith-eval` |
| Chậm hơn hẳn một agent | Các "agent" chạy tuần tự — đây là pipeline, không nên tách agent |

## Trước khi kết thúc task

- Đã trả lời được: vì sao **không** dùng một agent với tool tốt hơn?
- Mọi field trong shared state được quyết định có reducer hay ghi đè, có chủ ý.
- Worker nhận đúng nhiệm vụ, trả về tóm tắt.
- Có giới hạn số lần chuyển giao và số nhánh song song.
- Đã đo token trước/sau khi tách agent, không chỉ đoán.

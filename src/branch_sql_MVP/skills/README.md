# Skills cho agent coding — LangChain / LangGraph

Bộ skill cho Claude Code khi làm việc trên codebase dùng LangChain và LangGraph.
Mỗi skill nạp vào context khi task khớp `description` của nó, không phải lúc nào
cũng nằm sẵn trong prompt.

> **Vị trí thư mục.** Claude Code chỉ tự khám phá skill ở `.claude/skills/`
> (project) hoặc `~/.claude/skills/` (user). Thư mục này đang nằm ở
> `vi-coze/skills/` nên sẽ **không tự kích hoạt** — muốn dùng thì symlink/copy
> vào `.claude/skills/`, hoặc đọc thủ công như tài liệu tham chiếu.

## Tầng nền — LangChain / LangGraph

| Skill | Kích hoạt khi |
|---|---|
| `langchain-core` | Viết chain, gọi chat model, prompt template, structured output, tool, `create_agent` |
| `langgraph-workflows` | Xây graph nhiều bước, state, checkpointer, human-in-the-loop, streaming, subgraph |
| `langchain-rag` | Ingestion, splitter, vector store, retriever, rerank, RAG chain, tài liệu tiếng Việt |
| `langsmith-eval` | Tracing, dataset, `evaluate()`, LLM-as-judge, RAGAS |

## Tầng agent

| Skill | Kích hoạt khi |
|---|---|
| `agent-design` | Quyết định có nên dùng agent, chọn paradigm, lắp system prompt, dừng vòng lặp, tách plan/act |
| `agent-memory` | Checkpointer vs Store, trim/summarize lịch sử, long-term memory, context engineering |
| `agent-tools-mcp` | Viết tool description, quản lý nhiều tool, bảo mật tool, prompt injection, MCP server/client |
| `multi-agent` | Supervisor, handoff, fan-out song song, chia state, chi phí multi-agent |
| `agent-production` | Trajectory eval, observability, chi phí, deploy, durable execution, bảo mật |

## Thứ tự đọc khi xây agent mới

```
agent-design  ->  langgraph-workflows  ->  agent-tools-mcp
                          |                       |
                    agent-memory            multi-agent (chỉ khi cần)
                          |
                  agent-production
```

`agent-design` quyết định **có nên** làm; `langgraph-workflows` là **cách viết**;
`agent-production` là thứ phải xong **trước khi** ra thật.

## Nguyên tắc chung cho mọi skill

**Kiểm chứng version trước khi viết code.** LangChain đổi API nhanh; bộ skill
này viết theo `langchain>=1.0` / `langgraph>=1.0`. Chạy
`uv pip show langchain langgraph langchain-core` trước khi dùng bất kỳ pattern
nào. Nếu repo còn ở 0.x thì import path, `create_agent`, và tên checkpointer
(`MemorySaver` vs `InMemorySaver`) đều khác — đọc code hiện có làm chuẩn thay vì
áp pattern trong skill.

**Bám theo code sẵn có trong repo.** Nếu repo đã chọn một cách (LCEL thuần,
graph thủ công, hay `create_agent`), giữ nguyên cách đó thay vì trộn ba phong
cách trong một codebase.

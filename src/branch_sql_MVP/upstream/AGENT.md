# Trạng thái dự án — kb-text2sql

## Hoàn tất test-tuned ngày 2026-09-08

Luna hoàn tất 8 baseline × 99 câu, 8 alternative × 33 câu, mở rộng 4 alternative thêm 66 câu: 1.320 case-run hợp lệ, 16 cấu hình riêng. Token mới 8.706.990 = 7.927.768 input + 779.222 output; không còn reservation chưa đối soát, còn 293.010 so với trần 9M. Không tiếp tục gọi API sau khi hoàn tất search.

Kết quả gốc → được chọn (%): P1 58,16→58,16; hybrid 55,10→55,10; event-seeds 57,14→58,16 (top_k4); event-expansion 56,12→56,12; selector 53,06→57,14 (max_items12); B6-relational 54,08→56,12 (max_repairs2); B6-hybrid 56,12→57,14 (max_repairs2); G1 55,10→55,10. Cùng 99 câu/11DB, 98 câu chấm được vì gold card_games:518 timeout; run_error=0 trong mọi cấu hình cuối. Đây là test-tuned/in-sample, không phải holdout độc lập hay tối ưu toàn cục. G1 dùng difficulty metadata của dataset. Notebook `src/eval/test_optimization.ipynb`, bundle/ledger/raw runs `.runtime/luna_test_optimization_20260908`. 29 tests passed. Đã sửa khởi tạo Qdrant trước worker để tránh cold-cache race và tái sử dụng subset không ghi đè summary đầy đủ.

## Quyết định mới 2026-09-08: test-tuned, ngân sách mới 9M

Theo yêu cầu mới nhất, tối ưu trực tiếp trên test, giữ đủ 8 kịch bản trong 9 triệu token mới. Dùng 99 câu cố định lấy từ 307 internal test (phân tầng, seed42); screening 33 câu nằm trong chính 99 câu này. Vì đã dùng test để chọn cấu hình, kết quả là in-sample/test-tuned, không được gọi là holdout độc lập. Gold SQL/result chỉ ở evaluator, không đưa vào generation/repair/selector. 208 câu còn lại không chạy trong đợt này.

Chạy 8 baseline trước; thử một biến thể mỗi kịch bản trên 33 câu; ưu tiên hoàn tất biến thể cải thiện lên 99 câu trong phần ngân sách còn lại. Bảng cuối luôn có 8 kịch bản trên cùng 99 câu, chỉ chọn run đã hoàn chỉnh. Đây là tìm kiếm nhỏ theo ngân sách, không phải exhaustive optimization. Artifact mới `.runtime/luna_test_optimization_20260908`, notebook `src/eval/test_optimization.ipynb`; giữ nguyên artifact/ledger cũ.

## Dự toán ngày 2026-09-08 — chưa tăng ngân sách

Đã tính phần còn lại từ raw usage: dev khoảng 15–17M token; 8×307 internal test khoảng 15–19M; tổng dự phòng 30–36M token mới, 5–8 giờ tùy throughput. Chưa có quyền vượt trần cũ và chưa gọi Luna hôm nay. Notebook đã lưu căn cứ dự toán. Đã thêm reuse proxy từ bundle có cùng split/fingerprint/revision và trả cached summary trước khi ghi lại manifest của run hoàn chỉnh. 26 tests passed.

## Đợt Luna 9 triệu token — tạm dừng 2026-09-07

Đã thực chạy trên 99 câu dev cố định thuộc split nội bộ 1.227 dev / 307 test. Hoàn thành 17 run riêng biệt (1.683 case-run), thêm 15 case của `dev-B4-cd8f2c6c5509` đang dở ở `value_linking/values_off`. Năm stage đã chọn: reasoning high; hybrid dense 0,7/keyword 0,3; reranker bật top8/max_length256; retrieval candidate16/docs5; schema wide table8/column20. Cấu hình sau schema đạt 49/98 = 50% execution accuracy; một gold query codebase_community:701 timeout được ghi evaluation_error, không tính là model sai.

API xác nhận 7.854.498 input + 887.078 output = 8.741.576 token, bao gồm smoke. Ledger bảo thủ là 8.975.825/9.000.000, gồm 234.249 token dự phòng chưa đối soát từ request lỗi/gián đoạn. Không có tiến trình benchmark tiếp tục sau chốt ngân sách. Đây không phải xác nhận quota/billing toàn tài khoản.

Chưa chốt value linking, context budget, event expansion, selector, repair hoặc candidate bound; chưa chạy test. Không báo cáo best-so-far là cấu hình hoàn chỉnh. Raw runs và ledger nằm ở `.runtime/luna_internal_holdout_v1`; notebook `src/eval/internal_holdout.ipynb`. Khi được cấp quota mới, tiếp tục từ cache cùng split và cộng ngân sách mới vào trần ledger tích lũy; không xóa ledger hoặc tự reset theo ngày.

Concurrency của đợt chính là 6; lượt resume cuối là 1. Runner hiện ghi lại manifest khi resume, nên trường max_concurrency trong manifest là giới hạn yêu cầu cuối, không phản ánh đầy đủ lịch sử chạy. Không dùng latency của các run này để claim so sánh concurrency. Gold cache chỉ tồn tại trong evaluator, không đi vào workflow. Test cục bộ: 25 passed, Ruff passed.

## Điều chỉnh có hiệu lực 2026-09-07

Audit phát hiện 11 câu legacy test trùng question với dev, test legacy chỉ có 2 DB; không dùng kết quả cũ làm bằng chứng holdout độc lập. B5 cũ trùng cấu hình expansion (selector off); các nhãn Verified bên dưới là lịch sử và không đủ để nghiệm thu ablation hiện tại.

Protocol mới dùng split nội bộ khoảng 80/20 theo database/difficulty và nhóm câu hỏi, giữ câu đã có trong raw runs và câu trùng legacy ở phía dev. Manifest `src/eval/dataset_split.json` giữ ID nguồn, không di chuyển data. Đây là known-database question generalization, không phải official BIRD test hoặc unseen-database test. Mặc định tune tối đa 3 câu mỗi strata (99 câu); `--dev-per-stratum 0` dùng toàn dev pool. Chưa chạy API theo protocol mới.

Runner dùng cache theo cấu hình, không theo tên experiment; prompt sinh một ứng viên thống nhất; B5 đầy đủ bật selector, B6 relational dùng cùng cấu hình B5. Kết quả mới lưu riêng tại `.runtime/luna_internal_holdout_v1`, báo cáo tại `src/eval/internal_holdout.ipynb`. Mọi kết quả cũ giữ nguyên để audit. Tối ưu vẫn là coordinate search giới hạn ngân sách, không phải chứng minh global optimum; multiple replicates/CI và metric retrieval còn trong backlog.

Cập nhật lần cuối: 2026-09-04

## Vai trò của tài liệu

`AGENT.md` là trạng thái bền vững của dự án dành cho người phát triển và AI agent. Tài liệu này lưu tầm nhìn, quyết định kiến trúc, hiện trạng đã kiểm chứng, quy ước đặt tên và tiêu chí hoàn thành.

- `README.md` dành cho người sử dụng và hướng dẫn vận hành.
- `AGENT.md` mô tả dự án đang ở đâu và những quyết định nào đang có hiệu lực.
- `PLAN.md` chỉ mô tả công việc sắp tới, thứ tự thực hiện và điều kiện nghiệm thu.

Tên file số ít được giữ đúng theo yêu cầu của chủ dự án. Chuẩn Codex tự động nạp chỉ dẫn thường dùng `AGENTS.md`; vì vậy file này hiện là tài liệu state của dự án, không được giả định là cơ chế tự động nạp chỉ dẫn.

## Tầm nhìn

Xây dựng một hệ thống Vietnamese Text-to-SQL trên BIRD có thể benchmark công bằng từ prompt đầy đủ đến context engineering, execution repair và graph/agentic orchestration. Hệ thống phải tái lập được, chống rò rỉ gold SQL, đo được đóng góp của từng thành phần và giữ thuật toán nghiệp vụ tách khỏi lớp điều phối LangGraph.

Mục tiêu không phải chỉ tạo SQL chạy được. Hệ thống phải cho biết vì sao một cấu hình tốt hơn cấu hình khác thông qua execution accuracy, hiệu quả, retrieval/linking quality, chi phí, độ trễ và trajectory của workflow.

## Thang benchmark đã chốt

| ID | Tên mô tả | Phạm vi |
| --- | --- | --- |
| P1 | Full-context prompt baseline | Question + full DDL/schema + BIRD evidence, sinh SQL một lần |
| B4 | Hybrid linked context | Hybrid retrieval + schema linking + value linking + train-example linking |
| B5 | SAG relational context | B4 + event–entity indexing + query-time relational expansion + contextual evidence selection |
| B6 | Execution-guided repair | Generate → execute → observe → repair, tối đa 2–3 vòng |
| G1 | Adaptive graph workflow | Định tuyến thích nghi + ứng viên song song + shared state + selector |

Quan hệ benchmark:

- P1 là baseline prompt/context đầy đủ, không retrieval và không repair.
- B4 đo riêng đóng góp của hybrid retrieval và linking.
- B5 là một benchmark riêng để cô lập đóng góp của ý tưởng SAG; không gộp âm thầm vào B4.
- B6 chính sử dụng context đã đóng băng từ B5. Một ablation phụ có thể dùng B4 + execution repair để tách riêng lợi ích của repair.
- G1 chỉ được gọi là agentic nếu model có quyền quyết định bước tiếp theo hoặc tool tiếp theo. Nếu route được xác định hoàn toàn bằng luật, đây là adaptive workflow graph.

## Quyết định kiến trúc đang có hiệu lực

- Câu hỏi benchmark dùng tiếng Việt; business SQL và cấu trúc gold giữ sát định dạng BIRD.
- SQLite là nguồn thực thi chuẩn vì gold query của BIRD dùng SQLite dialect. Mọi truy vấn do model tạo phải chạy qua kết nối read-only và có timeout/giới hạn an toàn.
- Qdrant phục vụ dense vector, sparse/BM25 và hybrid retrieval. Qdrant không thay thế SQLite.
- Docker là môi trường chạy chuẩn.
- `uv` quản lý môi trường và thư viện.
- PyTorch phải là bản CUDA có thể dùng GPU; CPU fallback chỉ dành cho môi trường không có GPU và phải được ghi vào run manifest.
- LangGraph chỉ điều phối. Thuật toán truy xuất, linking, sinh SQL, thực thi và chấm chọn nằm trong `src/offline` hoặc `src/online` và có thể kiểm thử độc lập.
- Đồ thị entity/relation hiện có trong `src/offline/graph.py` không phải SAG. Hai loại đồ thị phải có artifact, schema và tên gọi riêng.
- Ba vai trò SQLite phải tách biệt: database BIRD chỉ đọc, checkpointer của workflow và store dài hạn nếu sau này thật sự cần. Không dùng một database cho cả ba vai trò.
- Nếu workflow cần checkpoint, mỗi câu benchmark có một thread riêng và checkpoint chỉ tồn tại trong runtime tạm. Không có memory xuyên câu và không ghi dữ liệu test vào long-term store.
- Gold SQL chỉ được dùng sau khi dự đoán đã được đóng băng, tại lớp evaluator. Không đưa gold SQL hoặc kết quả suy ra từ gold vào retrieval, prompt, repair, selector hay state của workflow.

## Hiện trạng đã kiểm chứng

### Mã nguồn

- `src/offline` đã có schema catalog, train-only example contract và event–entity index v3 bên cạnh pipeline extraction/index cũ.
- `src/online` đã tách context builder, schema/value linking, SAG retrieval, SQL sandbox, candidate selection và structured LLM boundary.
- `src/data` hiện có `__init__.py`, `catalog.py`, `database.py`, `service.py`.
- `src/pipeline` có 9 module LangGraph cho state/contracts, P1, B4, B5, B6, G1 và registry.
- `src/eval/benchmark.py`, `src/eval/text2sql.py` và `src/eval/run_text2sql_benchmark.py` sở hữu artifact preparation, runner có resume và SQLite result-equivalence evaluator.
- `src/online/retrieval.py` hỗ trợ dense, keyword, hybrid RRF và cross-encoder tùy chọn; adapter XLM-R dùng tokenizer gốc và inference CUDA có lock.
- `src/offline/graph.py` vẫn là graph/community tổng quát; SAG dùng artifact riêng trong `src/offline/event_index.py`.
- `src/data/catalog.py` tạo stable ID và `workflow_input()` không chứa gold SQL.
- Gold-sample chunking nhận diện case bằng `-- Query:`: câu query là retrieval child, còn nguyên block `Query + Evidence + SQL` là atomic parent được trả về khi child khớp. Chính sách này không cho phép đưa dev/test gold vào benchmark retrieval.
- Business chunking theo cấu trúc tài liệu: mỗi bảng dưới một heading H3 như `frpm` là một atomic chunk nguyên bảng; mỗi marker `- **Qn**:` là một atomic chunk độc lập. Hai loại này không bị cắt bởi `child_max`, `parent_max` hoặc `table_rows`.

### Dữ liệu

- `data/dev` là BIRD dev tiếng Việt: 1.534 trường hợp, 11 database, schema metadata, business context và 63 gold files.
- `data/test` chứa 62 case thuộc `financial` và `debit_card_specializing`; toàn bộ đã được chạy cho mỗi kịch bản benchmark.
- Gold files và trường `SQL` của dev/test là evaluator-only. Repository không có train split nên example retrieval bị khóa ở trạng thái unavailable; dev/test gold không được index làm example.
- Translation checkpoints, translation summary, SQL dump trùng với SQLite dev, ZIP nguồn, metadata macOS và runtime/processed cache đã bị xóa theo yêu cầu.
- Catalog, runner và evaluator đã phân biệt `dev`/`test`, có stable sample ID, dataset/index fingerprint và leakage boundary rõ ràng.

### Môi trường

- Dự án đã có cấu hình Docker, `uv` và nguồn PyTorch CUDA 12.8 trong `pyproject.toml`.
- Docker mount `data` read-only và dùng `.runtime` qua `tmpfs`; Qdrant local cache mặc định bị tắt.
- Dependency đã khóa đồng bộ ở nhánh 1.x: `langchain 1.3.18`, `langchain-core 1.6.1`, `langchain-openai 1.6.0`, `langgraph 1.2.11`; `langsmith 0.11.2`.
- `sentencepiece`, `nbformat`, `nbclient` và `ipykernel` đã được khai báo để chạy reranker và notebook có output.
- Máy benchmark đã kiểm chứng dùng PyTorch `2.11.0+cu128`, CUDA 12.8 và NVIDIA GeForce RTX 4050 Laptop GPU.

### Skills cục bộ

Đã đọc và đưa vào quyết định dự án các hướng dẫn trong:

- `skills/agent-design`
- `skills/langgraph-workflows`
- `skills/langchain-rag`
- `skills/agent-memory`
- `skills/agent-production`
- `skills/langsmith-eval`
- `skills/agent-tools-mcp`
- `skills/multi-agent`
- `skills/langchain-core`

Folder `skills/` ở root không tự động đồng nghĩa với việc mọi runtime/agent sẽ nạp skill. Trước mỗi thay đổi liên quan, người thực hiện phải đọc trực tiếp skill phù hợp và kiểm tra phiên bản package thực tế.

## Trạng thái triển khai benchmark

| Hạng mục | Trạng thái | Ghi chú |
| --- | --- | --- |
| uv + CUDA package routing | Đã kiểm chứng cục bộ | CUDA hoạt động; Docker GPU smoke vẫn còn trong plan rộng hơn |
| SQLite BIRD data access | Đã triển khai | Full DDL/PK/FK/value catalog, read-only authorizer, timeout và row limit |
| Qdrant hybrid retrieval | Đã triển khai | Local Qdrant, dense+sparse RRF, filter theo doc ID, reranker tùy chọn và trace |
| P1 | Đã benchmark với Luna | 62/62 test, execution accuracy 0,4355 |
| B4 | Đã benchmark với Luna | 62/62 test, execution accuracy 0,4355 |
| B5 | Đã benchmark và ablate với Luna | Seed 0,4839; expansion 0,4839; cấu hình relational đã khóa 0,3871 |
| B6 | Đã benchmark với Luna | Relational 0,4516; hybrid 0,4516; dev chọn `max_repairs=1` |
| G1 | Đã benchmark với Luna | 0,5000; dev chọn `max_candidates=1`; grid 1/2/3 đã chạy trên dev |

### Luna component tuning và full test ngày 2026-09-04

- Model sinh và chọn context là `openai/gpt-5.6-luna`; reasoning effort được dev chọn là `high`.
- Dev tuning dùng 33 case: với mỗi 11 database lấy đúng một case `simple`, một `moderate` và một `challenging`, seed 42. Tập dev đầy đủ có 1.534 case nhưng không được dùng hết để giới hạn chi phí.
- Test dùng toàn bộ 62 case cho 8 scenario/ablation, tổng 496 case-run; mọi scenario có `run_error_rate=0`.
- Coordinate search chọn: hybrid RRF cân bằng, tắt reranker, `candidate_k=16`, `docs_top_k=5`, `table_k=5`, `column_k=12`, `value_k=8`, fuzzy threshold `0.84`, context budget `5000`, `event_top_k=12`, `event_hops=2` và tắt contextual selector. Mỗi stage có no-change incumbent để không hạ trạng thái tốt nhất do stochastic rerun.
- Dev chọn `max_repairs=1` và `max_candidates=1`. Kết quả test không được dùng để sửa ngược tham số.
- Test execution accuracy: P1 0,4355; B4 fixed 0,4355; event seeds 0,4839; event expansion 0,4839; B5 relational 0,3871; B6 relational 0,4516; B6 hybrid 0,4516; G1 adaptive 0,5000.
- Notebook đã execute `9/9` code cell, không lỗi: `src/eval/luna_component_tuning.ipynb`. Bundle và raw runs nằm dưới `.runtime/text2sql_benchmark_multimodel/`.
- Tổng test dùng 2.334.798 input token và 307.702 output token; chi phí niêm yết ước tính khoảng 0,836 USD trước cache discount.
- Metric chính là `sqlite_result_equivalence_v1`. Official BIRD R-VES chưa tích hợp nên luôn để `None`, không thay thế bằng execution accuracy.

Nền tảng có sẵn không được báo cáo thành benchmark đã hoàn thành. Một benchmark chỉ hoàn thành khi chạy end-to-end, có manifest, metrics và test chống leakage.

## Ranh giới module

Luồng phụ thuộc chuẩn:

1. `src/data` sở hữu dataset discovery, database access và schema/value metadata.
2. `src/offline` tạo artifact có version: chunks, embeddings, indexes, example index và graph index.
3. `src/online` cung cấp các thao tác độc lập ở query time: linking, retrieval, generation, execution và selection.
4. `src/pipeline` chỉ ghép các thao tác thành P1, B4, B5, B6 và G1 bằng LangGraph.
5. Runner/evaluator chọn workflow qua registry và ghi run manifest; không nhúng logic benchmark vào tên hàm.

State của LangGraph chỉ chứa dữ liệu có thể serialize như ID, câu hỏi, evidence reference, SQL candidate, observation, số vòng và metric tạm thời. Không đặt client Qdrant, SQLite connection, model object hoặc callable vào state.

Retrieval core không được tự gọi LLM. Nếu cần query analysis hoặc contextual selector bằng LLM, đó phải là stage riêng, có tên riêng và trace riêng để đo retrieval mà không lẫn chi phí reasoning.

## Cấu trúc file benchmark đã triển khai

- `src/pipeline` có 9 file: `__init__.py`, `state.py`, `contracts.py`, `prompt_baseline.py`, `hybrid_context.py`, `sag_context.py`, `execution_repair.py`, `adaptive_workflow.py`, `registry.py`.
- `src/offline` đã bổ sung `schema_catalog.py`, `example_index.py`, `event_index.py`.
- `src/online` đã bổ sung `context_builder.py`, `schema_linking.py`, `sag_retrieval.py`, `sql_execution.py`, `candidate_selection.py`.

Ngoài 17 module trên, benchmark có runner/evaluator và notebook riêng trong `src/eval`.

## Quy ước đặt tên

Tên hàm và module phải mô tả hành vi nghiệp vụ, không mô tả số thứ tự benchmark.

Tên phù hợp gồm:

- `build_full_context`
- `link_schema_elements`
- `link_literal_values`
- `retrieve_similar_examples`
- `retrieve_hybrid_evidence`
- `identify_query_entities`
- `retrieve_seed_events`
- `expand_event_neighborhood`
- `select_evidence_bundle`
- `generate_sql_candidate`
- `execute_readonly_sql`
- `classify_execution_error`
- `repair_sql_candidate`
- `select_best_candidate`
- `build_workflow`

Không dùng các tên như `retrieve_b4`, `retrieve_b5`, `run_b6` hoặc `g1_node`. ID P1/B4/B5/B6/G1 chỉ xuất hiện trong registry, cấu hình benchmark, tên báo cáo và metadata của run.

Các quy ước code hiện có phải được giữ:

- Module docstring và thông báo lỗi dùng tiếng Việt.
- Type hint rõ ràng và `from __future__ import annotations` khi phù hợp với file hiện có.
- Public API ngắn, import nặng theo kiểu lazy khi cần.
- Dữ liệu biên LLM có structured schema; không parse bằng regex nếu có thể dùng schema validation.
- Node trả partial state update; không mutate state tại chỗ.
- Nhánh song song phải khai báo reducer cho mọi field có nhiều writer.
- Mọi loop có giới hạn vòng, timeout và terminal condition rõ ràng.

## Nguyên tắc SAG/B5

B5 chỉ được xem là lấy cảm hứng từ SAG khi có đủ các đặc điểm cốt lõi:

- Offline tạo event–entity representation riêng, không chỉ đổi tên graph hiện có.
- Query time xác định seed events/entities từ câu hỏi và B4 evidence.
- Expansion theo quan hệ bị giới hạn hop, số node và token budget.
- Contextual selector chọn evidence theo câu hỏi thay vì chỉ dùng similarity score tĩnh.
- Evidence đưa vào prompt phải map trở lại nguồn gốc ban đầu để audit được.
- Có ablation tách B4, B4 + event retrieval, B4 + expansion và B5 đầy đủ.

Không khẳng định tái tạo nguyên vẹn kết quả SAG hoặc SOTA nếu chưa chạy đúng dataset, metric và điều kiện của bài báo.

## Nguyên tắc workflow và agent

- P1, B4 và B5 là workflow cố định.
- B6 là workflow có vòng lặp điều kiện, giới hạn 2–3 lần repair. Việc có loop không tự động biến nó thành agent.
- G1 bắt đầu bằng một `StateGraph` và các worker song song. Chỉ tách multi-agent khi các vai trò cần context, tool hoặc vòng đời độc lập thật sự.
- `Send` phù hợp cho dynamic fan-out; reducer bắt buộc với candidate/result list.
- Checkpointer phục vụ khôi phục trong một run, không phải long-term memory.
- Trajectory phải được đánh giá cùng final SQL: route, số tool call, số repair, lỗi lặp, selector decision, latency và token usage.

## Tính toàn vẹn benchmark

- Mỗi case có stable ID gắn với database, split và ngôn ngữ.
- Chỉ train split được dùng làm example retrieval corpus.
- Index và artifact phải ghi dataset fingerprint, model/version, config và thời gian tạo.
- Mỗi run ghi model, prompt version, index version, seed, hardware, dependency lock, latency, token usage và lỗi.
- So sánh benchmark thay đổi một biến chính tại một thời điểm; cùng model, decoding và execution policy nếu biến đó không phải đối tượng nghiên cứu.
- Báo cáo tối thiểu execution accuracy, R-VES khi áp dụng được, invalid SQL rate, schema/value-linking recall, retrieval recall, số vòng repair, latency và chi phí.
- Selector không được xem gold SQL, gold result hay metric của evaluator.

## Quy trình làm việc bắt buộc

Trước khi sửa code:

1. Đọc `AGENT.md`, `PLAN.md` và skill liên quan.
2. Kiểm tra mã nguồn và dependency version thực tế; không giả định API theo trí nhớ hoặc theo skill.
3. Xác định benchmark/stage đang thay đổi và metric dùng để chứng minh thay đổi đó.
4. Ghi rõ giả định nếu dữ liệu hoặc yêu cầu chưa đầy đủ.

Trong khi sửa:

1. Giữ thay đổi trong đúng module ownership.
2. Không chép thuật toán vào LangGraph node nếu đã có thể gọi qua hàm online/offline độc lập.
3. Thêm test cho contract, nhánh lỗi, loop bound và leakage boundary.
4. Không sửa rộng ngoài phạm vi hoặc phá thay đổi hiện có của chủ dự án.

Sau khi sửa:

1. Chạy test và smoke test phù hợp.
2. Cập nhật bảng trạng thái này bằng sự thật đã kiểm chứng.
3. Cập nhật `PLAN.md`: hoàn thành, còn lại, blocker và quyết định mới.
4. Không đánh dấu hoàn thành chỉ vì file đã tồn tại.

## Định nghĩa hoàn thành

Một hạng mục được xem là hoàn thành khi:

- Contract đầu vào/đầu ra rõ ràng.
- Có unit test và ít nhất một end-to-end smoke test.
- Không rò rỉ gold hoặc state giữa các case.
- Chạy được trong môi trường Docker/uv mục tiêu.
- Có trace/manifest để tái lập.
- Metric liên quan đã được ghi và so sánh với baseline hợp lệ.
- `AGENT.md` và `PLAN.md` phản ánh đúng trạng thái mới.

## Tài liệu tham chiếu kiến trúc

- OpenAI Codex, quy ước `AGENTS.md`: https://github.com/openai/codex/blob/main/docs/agents_md.md
- OpenAI Codex, template lập kế hoạch: https://github.com/openai/codex/blob/main/codex-rs/collaboration-mode-templates/templates/plan.md
- LangGraph, hướng dẫn repository: https://github.com/langchain-ai/langgraph/blob/main/AGENTS.md
- Microsoft Agentic Journeys, pattern master plan: https://github.com/microsoft/agentic-journeys
- SAG paper: https://arxiv.org/abs/2606.15971
- Danh mục skill cục bộ: `skills/README.md`

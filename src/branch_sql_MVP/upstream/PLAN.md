# Kế hoạch dự án — kb-text2sql

## Scope hiện hành 2026-09-08: tối ưu trên test theo yêu cầu người dùng

Thay kế hoạch tiếp tục grid dev bằng 8 kịch bản test-tuned trên subset cố định 99/307 câu. Screening 33 câu thuộc cùng subset; không báo cáo như test độc lập. Trần đợt mới 9M token, ledger riêng và không xóa ledger cũ. Chạy đủ 8 baseline trước, rồi screening một biến thể mỗi kịch bản và hoàn tất các biến thể hứa hẹn nếu còn ngân sách. Giữ gold ở evaluator; chỉ dùng score để chọn thông số theo yêu cầu. Kết quả và mọi lựa chọn/skip do ngân sách phải lưu ở `src/eval/test_optimization.ipynb`.

## Tiến độ thực chạy 2026-09-07 — dừng theo ngân sách người dùng

17 run hoàn chỉnh trên 99 dev; reasoning, retrieval fusion, reranking, retrieval depth và schema linking đã chọn. Value linking/values_off lưu 15/99 câu; các stage tiếp theo và toàn bộ 307 internal test chưa chạy. Best-so-far sau schema là 50% trên 98 câu chấm được, một gold timeout ghi riêng. Không nghiệm thu cấu hình hoàn chỉnh hoặc test.

Người dùng yêu cầu giữ trần 9 triệu token và lưu để tiếp tục. Ledger dừng ở 8.975.825, usage API xác nhận 8.741.576; phần còn lại là dự phòng chưa đối soát. Muốn chạy tiếp cần quota mới được người dùng cấp; giữ ledger tích lũy và cache, không tự tăng trần. Khi resume, hoàn tất value/context/event/selector/repair/candidate trên dev rồi mới khóa và chạy tất cả test. Notebook canonical vẫn là `src/eval/internal_holdout.ipynb`.

Ngày 2026-09-08 đã sửa resume để giữ summary/manifest của run hoàn chỉnh và reuse proxy từ bundle cùng split/fingerprint/revision. Lịch sử concurrency đợt 07-09 là 6 rồi 1 và đã ghi trong AGENT/notebook. Evaluator báo coverage và loại gold execution error khỏi mẫu số accuracy; giữ cùng chính sách cho mọi kịch bản. Dự toán hoàn tất dev + test cần thêm 30–36M token; chưa tăng trần 9M khi chưa có xác nhận ngân sách mới.

## Hiệu chỉnh nghiệm thu 2026-09-07

Các trạng thái Verified ở bản 2026-09-04 bên dưới là lịch sử. B5 ablation và kết luận tối ưu cần kiểm chứng lại: test legacy có 11 câu trùng dev; hai run expansion/B5 cũ cùng cấu hình; sampling stochastic chưa có replicate.

Protocol đang có hiệu lực: split nội bộ khoảng 80/20 từ nguồn BIRD dev, phân tầng DB/difficulty, nhóm question không giao nhau, loại câu đã chạy và legacy khỏi internal holdout. Không đổi tên hoặc di chuyển nguồn dữ liệu. Dùng manifest cố định trong eval; 62 legacy chỉ làm regression. Tuning mặc định tối đa 99 câu để kiểm soát chi phí; full dev tùy chọn. Chạy toàn internal holdout chỉ sau khi khóa cấu hình, không dùng kết quả để tune lại. Các ID vẫn mang prefix dev theo nguồn; vai trò đánh giá ghi ở protocol/split manifest.

Đã sửa runner/cache và chuẩn bị notebook mới, chưa chạy model trả phí hoặc có accuracy mới. B5 đầy đủ bắt buộc bật contextual selector; B6 relational dùng cùng cấu hình context. G1 chọn candidate bound trên dev và phải báo cáo bound thực tế. Không tuyên bố lợi ích nhiều candidate nếu bound bằng 1. Các mục Docker, R-VES, CI/replicate, fault injection và retrieval/value recall vẫn chưa nghiệm thu.

Cập nhật lần cuối: 2026-09-04

## Mục đích và phạm vi

Tài liệu này chỉ nêu nhiệm vụ, thứ tự triển khai, quy tắc, tiêu chí nghiệm thu và quyết định cần chốt. Tài liệu không chứa code, pseudo-code, generated SQL, lệnh shell hoặc đoạn cấu hình.

Phải đọc `AGENT.md` trước khi thực hiện kế hoạch. Khi trạng thái thực tế thay đổi, cập nhật `AGENT.md` trước hoặc cùng lúc với việc cập nhật kế hoạch này.

Các trạng thái sử dụng trong kế hoạch:

- Planned: đã xác định nhưng chưa bắt đầu.
- In progress: đang triển khai và có người chịu trách nhiệm.
- Blocked: có blocker cụ thể, được ghi rõ.
- Verified: đã đạt toàn bộ tiêu chí nghiệm thu.
- Deferred: chủ động để sau, không được hiểu là hoàn thành.

## Luật bắt buộc

1. Yêu cầu mới nhất của chủ dự án là nguồn quyết định cao nhất trong phạm vi công việc.
2. Tên code phải mô tả trách nhiệm nghiệp vụ. Không dùng P1, B4, B5, B6 hoặc G1 làm tên hàm/node nghiệp vụ.
3. Bám sát phong cách hiện có: module nhỏ, functional core, type hint rõ, docstring và lỗi tiếng Việt, lazy import khi dependency nặng.
4. LangGraph chỉ điều phối các hàm từ `src/data`, `src/offline` và `src/online`; không chứa bản sao thuật toán, prompt lớn hoặc database logic.
5. Graph hiện có và SAG event–entity graph là hai subsystem khác nhau; không tái sử dụng tên artifact gây nhập nhằng.
6. Giữ SQLite cho BIRD execution và Qdrant cho vector/sparse/hybrid retrieval.
7. Giữ Docker, `uv` và PyTorch CUDA làm nền tảng môi trường.
8. Không dùng gold SQL, gold execution result hoặc test-derived fact trong context, retrieval, repair hay selection.
9. Không có memory xuyên benchmark case. Mỗi case có thread/checkpoint riêng.
10. Mỗi benchmark phải thay đổi một biến chính để có thể quy kết chênh lệch metric.
11. Mọi loop có giới hạn vòng; mọi truy vấn có read-only policy, timeout và giới hạn tài nguyên.
12. Không sửa file ngoài phạm vi, không xóa thay đổi của người dùng và không thực hiện refactor lớn nếu chưa phục vụ milestone hiện tại.
13. Chỉ cập nhật trạng thái Verified khi có test, smoke run, manifest và metric theo tiêu chí.
14. Trước khi dùng LangChain/LangGraph, đọc skill liên quan và kiểm tra version package thực tế.
15. Chỉ gọi một hệ thống là agentic khi model thật sự quyết định tool hoặc bước tiếp theo; route theo luật là workflow.
16. Retrieval core không gọi LLM. Query analysis hoặc contextual selection dùng LLM phải là stage độc lập để trace và đánh giá riêng.

## Trạng thái milestone hiện tại

Mục tiêu Luna component-tuning/test-comparison đã hoàn thành ngày 2026-09-04 sau khi khóa semantic chunk contract. Kế hoạch rộng hơn còn Docker GPU smoke, official R-VES, multiple seeds/confidence interval và fault injection.

Nền tảng đã có:

- Docker và `uv` đã được khai báo trong dự án.
- PyTorch đã được định tuyến tới CUDA 12.8 trong cấu hình dependency.
- SQLite read-only helper đã tồn tại.
- Offline extraction/chunking/embedding/indexing và graph tổng quát đã tồn tại.
- Online dense, keyword, hybrid retrieval và reranking đã tồn tại một phần.
- Bộ `bird_dev_vi` và tài liệu dịch đã tồn tại.
- Thang benchmark P1, B4, B5, B6, G1 đã được chốt về mặt khái niệm.
- `AGENT.md` và `PLAN.md` đã được thiết lập làm project state và forward plan.

Các mục trên là nền tảng, không có nghĩa các benchmark end-to-end đã hoàn thành.

## Giai đoạn 1 — Khóa dependency, dữ liệu và evaluator

Trạng thái: In progress — local uv/CUDA, contract và evaluator đã kiểm chứng; Docker GPU smoke còn lại

### Mục tiêu

- Chọn một chiến lược version thống nhất cho LangChain/LangGraph.
- Hoàn thiện stable sample ID cho `data/dev`; split discovery và SQLite mapping đã có.
- Chuẩn hóa full DDL, primary key, foreign key và schema metadata cho từng database.
- Xây value inventory an toàn, có giới hạn cardinality và provenance.
- Xác định train-only example corpus; không cho dev/test example lọt vào index.
- Xác định contract prediction, run manifest và evaluator trước khi viết workflow.

### Quyết định version cần chốt

Môi trường hiện tại có `langchain-core 0.3.86`, chưa có `langchain` và `langgraph`, trong khi skills mới hướng tới API 1.x. Chỉ được bắt đầu code LangGraph sau khi chọn một trong hai hướng:

- Nâng đồng bộ lên một bộ package 1.x tương thích và cập nhật lockfile.
- Giữ core 0.x có chủ đích, chọn LangGraph tương thích và điều chỉnh hướng dẫn skill theo API thực tế.

Không trộn ví dụ 1.x với dependency 0.x.

### Tiêu chí nghiệm thu

- Dependency resolver thành công trong Docker và môi trường uv cục bộ.
- Import smoke test cho LangChain core, LangGraph, Qdrant và PyTorch thành công.
- GPU smoke test ghi rõ CUDA availability, device và PyTorch build.
- Dataset discovery trả đủ 1.534 case và 11 database, không trùng stable ID.
- Mỗi case ánh xạ đúng question, evidence, database và gold file mà evaluator giữ riêng.
- Full DDL có table, column, type, primary key và foreign key nhất quán với SQLite.
- Run manifest có đủ model, prompt, dataset/index fingerprint, seed, hardware và dependency lock.

## Giai đoạn 2 — P1 full-context baseline

Trạng thái: In progress — full test 62 case đã chạy; full dev run theo tiêu chí gốc chưa chạy

### Mục tiêu

- Xây full-context bundle từ question, DDL/schema và BIRD evidence.
- Chuẩn hóa structured SQL prediction và lỗi từ LLM boundary.
- Tách generation khỏi retrieval hiện có.
- Chạy one-shot, không repair, không hidden retry và không selector.
- Thiết lập baseline về execution accuracy, invalid SQL, latency, token và chi phí.

### Tiêu chí nghiệm thu

- P1 chạy end-to-end trên một smoke subset và full dev run có thể resume.
- Context được lưu bằng reference/manifest có thể audit.
- Không có training example retrieval hoặc Qdrant retrieval trong P1.
- Mỗi case chỉ có một lần generation được tính vào prediction chính.
- Evaluator chỉ nhận gold sau khi prediction đã đóng băng.

## Giai đoạn 3 — B4 hybrid linked context

Trạng thái: In progress — full test đã chạy; dense-only/sparse-only và value-link recall riêng còn lại

### Mục tiêu

- Chuẩn hóa dense, sparse/BM25, fusion và reranking thành retrieval contract độc lập.
- Thêm schema linking theo table, column, description và FK path.
- Thêm value linking với exact, normalized, fuzzy và semantic evidence có provenance.
- Thêm similar-example retrieval chỉ từ train split.
- Tạo evidence bundle theo token budget và deterministic ordering.
- Ghi retrieval/linking trace trước khi gọi LLM.

### Tiêu chí nghiệm thu

- B4 dùng cùng generation policy với P1; biến chính là context selection/linking.
- Có retrieval recall, schema-linking recall, value-linking recall và evidence provenance.
- Context không chứa duplicate hoặc item vượt budget mà không được ghi nhận.
- Không có execution feedback hoặc repair trong B4.
- Có ablation cho dense, sparse và hybrid trên cùng corpus/version.

## Giai đoạn 4 — B5 SAG relational context

Trạng thái: Verified

### Mục tiêu

- Xây event–entity artifact offline tách khỏi graph/community hiện có.
- Ánh xạ mỗi event/entity/edge về evidence nguồn ban đầu.
- Xác định seed event/entity từ question và B4 evidence.
- Thực hiện relational expansion theo hop, node budget và token budget giới hạn.
- Đặt contextual selector dùng LLM thành một online stage riêng, không nhúng vào retrieval core.
- Hợp nhất evidence mở rộng với B4 bundle bằng contract có provenance.

### Ablation bắt buộc

- B4 chuẩn.
- B4 cộng event retrieval nhưng chưa expansion.
- B4 cộng event retrieval và expansion nhưng chưa contextual selector.
- B5 đầy đủ.

### Tiêu chí nghiệm thu

- B5 không chỉ đổi tên graph cũ và không chỉ thêm một retriever nữa.
- Mọi graph item trong prompt truy ngược được về tài liệu, schema hoặc example nguồn.
- Expansion mặc định giới hạn một hop; thay đổi hop là một thí nghiệm riêng.
- Selector không thấy gold và có trace về item giữ, bỏ và lý do.
- Không có execution feedback hoặc SQL repair trong B5.

## Giai đoạn 5 — B6 execution-guided repair

Trạng thái: Verified cho single-run Luna — dev đã thử bound 0/1/2/3, chọn 1; notebook có first-pass/success/regression

### Mục tiêu

- Thực thi SQL candidate trong SQLite read-only sandbox.
- Chuẩn hóa observation theo syntax, schema, missing object, type/value, timeout, empty result và success.
- Repair có lịch sử candidate/observation nhưng không có gold.
- Giới hạn tối đa 2–3 vòng theo cấu hình benchmark.
- Dừng sớm khi thành công hoặc khi lặp lại candidate/lỗi không tiến triển.
- Benchmark chính dùng B5 context đã đóng băng; benchmark phụ dùng B4 context để đo riêng repair.

### Tiêu chí nghiệm thu

- Không có write statement, multi-statement hoặc truy vấn vượt timeout lọt qua execution policy.
- Loop bound có unit test và trajectory test.
- Báo cáo first-pass accuracy, final accuracy, repair success, regression after repair, vòng trung bình và latency tăng thêm.
- Context không được retrieval lại giữa các vòng trong benchmark chính, trừ khi khai báo một ablation riêng.
- Mỗi observation đủ cấu trúc để phân tích lỗi mà không lộ gold result.

## Giai đoạn 6 — G1 adaptive graph workflow

Trạng thái: Verified cho single-run Luna — dev đã thử candidate bound 1/2/3, chọn 1; notebook có route/trajectory breakdown

### Mục tiêu

- Thiết kế typed, serializable shared state với reducer cho field song song.
- Route theo độ khó và chất lượng context; ghi rõ route nào theo luật và route nào do model quyết định.
- Sinh nhiều SQL candidate song song với controlled diversity.
- Thực thi candidate an toàn và thu observation độc lập.
- Chọn candidate tốt nhất bằng tín hiệu không chứa gold.
- Dùng checkpoint cho khả năng resume trong cùng case.
- Bắt đầu bằng một StateGraph và các worker node; chưa tách multi-agent nếu chưa có bằng chứng cần context/tool độc lập.

### Tiêu chí nghiệm thu

- Parallel fan-out/fan-in không mất state và có reducer test.
- Mọi nhánh đều có terminal condition, timeout và candidate budget.
- Cùng seed/config tạo cùng graph topology và manifest; phần model không deterministic phải được ghi nhận.
- Selector có benchmark oracle-free và không thiên vị candidate theo vị trí.
- Có trajectory evaluation cho route, tool call, repair, loop, latency và token.
- Chỉ gắn nhãn agentic nếu model thực sự điều khiển ít nhất một quyết định hành động.

## Giai đoạn 7 — Benchmark, độ bền và báo cáo

Trạng thái: In progress — notebook Luna 8 scenario/496 case-run đã execute; R-VES, multiple seeds/CI và fault injection còn lại

### Mục tiêu

- Chạy P1 → B4 → B5 → B6 → G1 trên cùng snapshot dữ liệu và evaluator.
- Báo cáo execution accuracy và R-VES khi tương thích với protocol BIRD đang dùng.
- Phân tích theo database, độ khó, số table, join depth, evidence dependency và error taxonomy.
- Đo retrieval/linking riêng khỏi generation.
- Thêm fault injection cho timeout, malformed tool result, empty retrieval, Qdrant unavailable và checkpoint resume.
- Ghi rõ điều kiện phần cứng, model, prompt, index và chi phí.

### Tiêu chí nghiệm thu

- Mỗi bảng kết quả có run ID và manifest có thể tái lập.
- Có confidence interval hoặc nhiều seed khi model/config có tính ngẫu nhiên đáng kể.
- Không chuyển trực tiếp claim SOTA từ SAG hoặc repo khác sang hệ thống này.
- Có bảng ablation chứng minh đóng góp riêng của context, SAG, repair và graph orchestration.
- Failure analysis gắn với trace thực tế, không chỉ dựa trên final score.

## Hàng đợi công việc gần nhất

1. Tích hợp official BIRD R-VES evaluator hoặc giữ `None` nếu protocol test cũ không tương thích.
2. Chạy nhiều seed/replicate để lượng hóa phương sai của generation và tránh chọn bound từ một mẫu nhỏ.
3. Chạy full dev nếu ngân sách cho phép; Luna benchmark hiện dùng 33 case dev cân bằng theo 11 database × 3 difficulty và 62 case test để báo cáo.
4. Thêm dense-only, sparse-only, value-link recall và failure analysis theo join depth/evidence dependency.
5. Thêm fault injection cho timeout, malformed structured output, Qdrant unavailable và checkpoint resume.
6. Smoke test Docker với NVIDIA runtime; local uv/CUDA đã qua.

Notebook canonical cho Luna run hiện tại là `src/eval/luna_component_tuning.ipynb`; raw runs nằm trong `.runtime/text2sql_benchmark_multimodel/runs/` và có thể resume theo stable ID.

Luna run ngày 2026-09-04 chọn trên dev: reasoning `high`, hybrid cân bằng, tắt reranker, depth 5, schema balanced, value 8/ngưỡng 0,84, context 5k, event 12×2, tắt selector, repair bound 1 và candidate bound 1. Trên 62 case test, execution accuracy lần lượt là P1 43,55%; B4 fixed 43,55%; event seeds 48,39%; event expansion 48,39%; B5 relational 38,71%; B6 relational 45,16%; B6 hybrid 45,16%; G1 adaptive 50,00%. Cả tám run đều hoàn thành 62/62 case và có run-error rate 0.

Gold sample parent–child đã được kiểm chứng trên `california_schools/aggregation.sql`: mỗi marker `-- Query:` tạo đúng một query child và một atomic parent chứa đầy đủ Query, Evidence, SQL. Chỉ corpus train/reference độc lập mới được phép index loại chunk này trong benchmark.

Business semantic chunking đã được kiểm chứng trên `data/dev/business/california_schools.md`: ba bảng (`frpm`, `satscores`, `schools`) tạo ba atomic chunk nguyên bảng và 55 marker Q tạo 55 atomic rule chunk. Riêng `frpm` chỉ có một chunk dài 2.246 ký tự, chứa cả cột cuối; Q0 chỉ có một chunk nguyên văn. Artifact/index đã được rebuild và benchmark đã chạy lại; chunk contract hiện được ghi vào bundle/notebook và tham gia tạo fingerprint/run ID để không resume nhầm kết quả cũ.

## Quy tắc thay đổi kế hoạch

- Khi yêu cầu mới thay đổi scope, ghi quyết định và tác động vào `AGENT.md` trước khi đổi thứ tự phase.
- Khi một phase bị Blocked, ghi blocker cụ thể, bằng chứng đã kiểm tra và điều kiện gỡ blocker.
- Khi phát hiện file mới sẽ trùng trách nhiệm file hiện có, cập nhật dự kiến cấu trúc trước khi tạo file.
- Khi dependency hoặc dataset thay đổi, invalidation của artifact/index phải được ghi rõ.
- Khi chọn metric hoặc protocol BIRD khác, lưu cả phiên bản evaluator và lý do.
- Không xóa lịch sử quyết định quan trọng; chuyển nội dung lỗi thời sang ghi chú thay thế ngắn nếu cần.

## Tài liệu phải đối chiếu khi triển khai

- `AGENT.md` và `README.md` của dự án.
- Skill cục bộ phù hợp trong `skills/`.
- Tài liệu chính thức LangGraph/LangChain tương ứng với version đã khóa.
- Tài liệu SQLite, Qdrant, Docker, uv và PyTorch tương ứng với dependency lock.
- BIRD benchmark protocol đang dùng.
- SAG paper và repository SAG chỉ cho phạm vi B5; mọi khác biệt triển khai phải được ghi rõ.
- Các convention tham khảo từ OpenAI Codex, LangGraph và Microsoft Agentic Journeys được liệt kê trong `AGENT.md`.
## Kết quả hoàn tất 2026-09-08

Hoàn tất protocol test-tuned 8 kịch bản trên 99 câu, screening 8 biến thể trên 33 câu, mở rộng đủ 4 biến thể triển vọng lên 99 câu. 1.320 case-run hợp lệ; tổng 8.706.990/9.000.000 token mới. Cấu hình được chọn và mọi bảng thông số/metrics nằm trong `src/eval/test_optimization.ipynb`; raw data nằm `.runtime/luna_test_optimization_20260908`. Không tuyên bố test độc lập: 99 câu này đã dùng để tuning, 208 câu còn lại chưa chạy. Search đã hoàn tất trong phạm vi đã thông báo; không mở thêm lượt API.

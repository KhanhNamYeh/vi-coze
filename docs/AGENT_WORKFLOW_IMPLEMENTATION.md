# Đặc tả giao việc: node dùng chung và Studio offline/online

Trạng thái: **kế hoạch thực hiện, chưa phải tính năng đã có**. Ngày soạn: 2026-09-09.

Tài liệu này là chỉ dẫn triển khai cho agent code. Đọc hết trước khi sửa. Làm tuần tự các mốc; mỗi mốc phải có bằng chứng kiểm tra. Không đánh dấu hoàn thành chỉ vì giao diện đã vẽ được.

## 1. Mục tiêu và cách hiểu bắt buộc

Người dùng cần một app có thể cấu hình và chạy pipeline bằng các node nhỏ dùng chung, theo cách tổ chức của Dify. Offline và online cùng UI, cùng cơ chế cấu hình và quan sát. Dify là tham khảo cách tương tác, không phải yêu cầu cài hoặc sao chép toàn bộ Dify.

**Node type** là implementation dùng chung. **Node instance** là một vị trí trong pipeline, có ID, prompt và cấu hình riêng. **Pipeline** là cấu hình các instance và kết nối. **Run** là một lần thực thi một phiên bản pipeline trên một phiên bản dataset.

Ví dụ đúng: `sql_generate` và `sql_repair` đều có `type: llm`, chạy qua cùng implementation LLM, khác prompt và input mapping. Ví dụ sai: viết `GenerateSQLNode` và `RepairSQLNode` với hai bản code gọi model rồi gọi đó là tái sử dụng.

Không tách mọi hàm Python thành node. Tách khi người dùng cần cấu hình, nối biến, chạy thử hoặc quan sát bước đó. Hàm render chuỗi, parse dữ liệu và tiện ích nhỏ vẫn là hàm nội bộ.

Mục tiêu cuối: upload dữ liệu → chạy offline → chọn dataset ở online → sửa prompt node → chạy → thấy SQL, dữ liệu và câu trả lời. Không cần CLI hoặc lịch sử eval để hoàn thành luồng sử dụng chính.

## 2. Phạm vi và những việc không được làm

- Code chính nằm trong `src/branch_sql_MVP`. Không tạo nhánh thư mục thứ hai `src/branch/_sql/_MVP`.
- Giữ code nghiệp vụ, setting, dữ liệu và tối ưu đã chuyển từ kb-text2sql. Đọc hàm cũ rồi bọc/tách có kiểm chứng; không viết lại thuật toán retrieval/embedding theo phỏng đoán.
- Không sửa `.env`, không đưa API key vào JSON workflow, trace, Git hoặc frontend storage.
- Giữ default provider/model hiện tại: Google / `gemini-3.5-flash-lite`. Mọi instance LLM có thể kế thừa hoặc override.
- Không xóa runtime/dataset hoặc ghi đè database nguồn. Không reset thay đổi Git có sẵn.
- Không dựng workflow giả bằng timer, danh sách node hardcode ở frontend hoặc phát lại eval để thay cho lần chạy mới.
- Không hoàn thành bằng iframe Gradio. UI chính phải gọi API và dùng chung dataset/settings/run.
- Không biến nhiệm vụ thành xây toàn bộ Dify: không thêm marketplace, multi-tenant, arbitrary Python execution, deployment cloud hoặc connector database từ xa.
- SQLite là database được hỗ trợ trong phạm vi này. CSV/Excel chỉ là nguồn cần chuyển đổi trước; không hứa hỗ trợ DB trực tiếp nếu chưa triển khai.
- Không tự bật GraphRAG, tăng số ứng viên hoặc thay preset để tuyên bố chất lượng tốt hơn.
- Không commit/push/deploy khi chưa có yêu cầu. Khi kết thúc, dừng tiến trình app do agent khởi chạy để người dùng tự chạy.

## 3. Bản đồ code cần đọc trước

| File/thư mục | Vai trò hiện tại và lưu ý |
|---|---|
| `pipeline/registry.py` | Năm builder cho tám preset |
| `pipeline/presets.json` | Cấu hình cần bảo toàn; ID hiển thị không luôn trùng scenario |
| `pipeline/state.py` | State lớn dùng chung, chưa phải contract từng node |
| `pipeline/prompt_baseline.py`, `hybrid_context.py`, `sag_context.py` | Các pipeline sinh SQL |
| `pipeline/execution_repair.py`, `adaptive_workflow.py` | Loop repair và Send fan-out/fan-in |
| `online/llm.py`, `online/api.py` | Prompt viết cứng, structured output, provider adapter |
| `online/context_builder.py`, `sag_retrieval.py`, `sql_execution.py` | Nghiệp vụ cần tái sử dụng |
| `offline/` | Các bước preprocess/extract/link/chunk/embed/graph/index và schema/event |
| `data/import_dataset.py` | Import riêng với registry `.runtime/studio/datasets`; hiện ép graph disabled |
| `app/app.py` | FastAPI, API offline hiện có và Gradio cũ |
| `app/studio.py` | API online, graph, run stream; có nhánh lịch sử benchmark |
| `app/static/studio.html` | Studio mới; offline hiện được nhúng bằng iframe |
| `settings.py`, `settings.json` | Nguồn cấu hình hiện có; phải kiểm kê toàn bộ trường |
| `tests/test_text2sql_benchmark.py`, `test_studio.py`, `test_fresh_setup.py` | Regression tests trong thư mục MVP |

Đường dẫn trong bảng tính từ `src/branch_sql_MVP`, trừ khi ghi rõ khác. Không sửa `upstream/PLAN.md` để coi đó là kế hoạch hiện hành.

Các sự thật phải bảo toàn khi chuyển đổi:

- P1/B4/B5 hiện chỉ sinh SQL. B6/G1 thực thi SQL trong pipeline.
- B4-event-seeds và B4-event-expansion dùng builder B5; selector lần lượt tắt như preset.
- G1 mặc định hiện chỉ một ứng viên; code hỗ trợ nhiều ứng viên.
- Event index từ schema/nghiệp vụ khác với GraphRAG cũ. Không coi hai thứ là cùng một artifact.
- `llm.system_prompt` hiện phục vụ chat cũ, không phải prompt mọi node.
- API `/datasets` cũ là catalog benchmark; registry dataset import là nguồn khác. Phải có adapter thống nhất, không âm thầm trộn ID.

## 4. Kiến trúc đích

### 4.1 Bố trí đề nghị

Tạo `workflow/` trong MVP, gồm `contracts.py`, `registry.py`, `compiler.py`, `runtime.py`, `store.py`, `nodes/`, `templates/`. Tên module có thể điều chỉnh nếu repo có quy ước phù hợp, nhưng trách nhiệm không được nhập hết vào một file.

- `contracts`: model validate workflow, node, reference, run/event/output.
- `registry`: khai báo type, config schema, input/output schema, executor duy nhất cho mỗi type.
- `compiler`: validate và chuyển definition sang LangGraph thật.
- `runtime`: thực thi, event, lỗi, loop/fan-out, snapshot cấu hình.
- `store`: version workflow, run metadata, artifact references.
- `nodes`: adapter gọi nghiệp vụ hiện có.
- `templates`: tám pipeline mẫu và offline mẫu, không chứa eval artifacts/path máy cá nhân.

Các wrapper builder cũ được phép giữ để tương thích benchmark, nhưng phải gọi compiler/node mới. Không giữ hai implementation nghiệp vụ độc lập lâu dài.

### 4.2 Contract tối thiểu

Workflow: `schema_version`, `id`, `revision`, `kind` (offline/online), `nodes`, `edges`, `outputs`, `defaults`.

Node instance: `id`, `type`, `label`, `config`, `inputs`, `position`. `position` chỉ phục vụ UI, không ảnh hưởng thực thi.

Reference có cấu trúc, ví dụ `{"node_id":"context","output":"text"}`; literal dùng `{"value":"..."}`. Không dùng `eval` để giải biến.

Ví dụ instance (schema minh họa phải được hoàn chỉnh và dùng nhất quán ở code/tests/API):

```json
{
  "id": "sql_generate",
  "type": "llm",
  "label": "Sinh SQL",
  "config": {
    "system_prompt": "Sinh đúng một SELECT/WITH SQLite từ context.",
    "user_prompt": "Ngữ cảnh: {{context}}\nCâu hỏi: {{question}}",
    "response_format": "json",
    "output_schema": {
      "type": "object",
      "properties": {"sql": {"type": "string"}},
      "required": ["sql"]
    }
  },
  "inputs": {
    "context": {"node_id": "context", "output": "text"},
    "question": {"node_id": "start", "output": "question"}
  },
  "position": {"x": 500, "y": 100}
}
```

Node LLM luôn có output chuẩn `text`, `json`, `usage`, `model`, `latency`; node sau tham chiếu JSON theo đường dẫn được validate, ví dụ `json.sql`. Schema output của từng instance là cấu hình, không cần executor riêng.

State/run phải chứa run ID, workflow revision, dataset revision, snapshot setting hiệu lực và output theo **instance + invocation**. Loop/fan-out không được ghi đè cùng node ID. Reducer merge phải giữ mọi invocation và phát hiện collision; không dùng merge last-writer-wins để che xung đột.

Run chỉ đưa dữ liệu nhỏ cần thiết vào state. Artifact lớn lưu file có ID, checksum và metadata. SQL result có `candidate_id`, `columns`, `rows` bị giới hạn, `row_count_returned`, `truncated`, `status`, `error`. Không trình bày số dòng bị giới hạn như tổng số dòng database.

### 4.3 Quy tắc thực thi

- Validate trước chạy: type tồn tại, ID duy nhất, reference hợp lệ, input bắt buộc, kiểu tương thích, output schema và nhánh hợp lệ.
- Chu trình chỉ hợp lệ qua loop có giới hạn. Giữ hành vi repair và Send fan-out/fan-in hiện có.
- Nhánh loại trừ và gộp kết quả song song là hai hành vi khác nhau; không triển khai chung một barrier khiến nhánh không được chọn bị chờ mãi.
- Mỗi run đóng băng cấu hình: workspace → workflow → node → override được phép cho lần chạy. Ghi rõ trường nào nhận override; API key chỉ tham chiếu/bộ nhớ.
- Sửa setting trong khi run đang chạy không thay đổi run đó.
- Không tự retry lỗi ghi index như retry LLM; bước có side effect phải có khóa/idempotency phù hợp.
- Cấu hình và run history sống qua restart. Run bị ngắt phải đánh dấu interrupted, không tự hiện success hoặc tự chạy lại LLM.

## 5. Danh mục node phải có

| Type/chức năng | Phạm vi |
|---|---|
| Start / Output | Input người dùng và output cuối |
| LLM | Sinh SQL, repair, selector, router, chọn ứng viên, diễn giải; một executor |
| Retrieval | Truy hồi với adapter nghiệp vụ cũ |
| Schema/value linking | Liên kết bảng/cột/literal; tách thêm nếu cần cấu hình riêng |
| Event seeds / expansion | Dùng artifact event, hiển thị tham số rõ |
| Context builder | Ghép, deduplicate, giới hạn context; hỗ trợ full/linked |
| SQL executor | Read-only, timeout, row cap, kết quả có cấu trúc |
| Condition / branch merge | Rẽ nhánh và gom nhánh loại trừ |
| Bounded loop / candidate fan-out & collect | Tương đương loop repair và G1 hiện có |
| Offline adapters | Validate source, preprocess, schema, event index, extract, link, chunk, embed, graph, index, register dataset |

LLM được phép dùng chung cho offline và online nếu bước đó gọi model. Embed/rerank không phải LLM node. Không bọc toàn bộ `offline.pipeline.run()` thành một node rồi coi đã tách offline.

## 6. Các mốc thực hiện — làm đúng thứ tự

### M0 — Kiểm kê và baseline

1. Đọc hướng dẫn repo áp dụng, `git status`, các file mục 3.
2. Tạo bảng ánh xạ từng node cũ → hàm nghiệp vụ → type mới → input/output → setting đang dùng.
3. Kiểm kê từng field Settings: UI nào hiển thị, API nào lưu, consumer nào đọc. Field chỉ phục vụ eval phải ghi đúng phạm vi.
4. Chạy regression mục 9. Phân biệt lỗi môi trường với lỗi code.

**Xong khi:** có bảng ánh xạ và baseline; chưa mất hoặc thay đổi thuật toán cũ.

### M1 — Contracts, registry, compiler và lưu phiên bản

1. Implement contract và validation mục 4.
2. Implement registry có metadata schema để UI lấy danh sách node.
3. Implement compiler cho tuyến tính, condition/merge rồi loop/fan-out; dùng LangGraph thật.
4. Tách template tracked trong Git và bản người dùng trong runtime; lưu atomically, kiểm tra revision khi ghi để tránh mất chỉnh sửa.
5. Run lưu revision/snapshot, trace theo invocation; không serialize secret.

**Xong khi:** hai instance cùng type có output riêng; reference sai bị chặn; loop có bound; workflow save/reload giữ nguyên; sửa draft không đổi run cũ.

### M2 — Node LLM dùng chung

1. Gọi provider adapter hiện có. Tách prompt construction ra khỏi các hàm SQL chuyên biệt.
2. Hỗ trợ system/user prompt, input variables, model inheritance/override, text/JSON schema.
3. Kiểm tra biến thiếu trước gọi model; prompt preview hiển thị bản đã resolve bằng dữ liệu thử.
4. Hỗ trợ timeout/retry có giới hạn và error output thống nhất.
5. Chuyển prompt cũ thành template instance; giữ confidence/assumptions/usage mà consumer cần.
6. Cho chạy riêng node với explicit test input hoặc upstream output của run đã chọn. Không tự chạy ngầm toàn bộ upstream.

**Xong khi:** một pipeline có hai LLM instance prompt/model khác nhau; mock provider chứng minh đúng message và model đến từng call. JSON sai báo lỗi tại đúng node.

### M3 — Chuyển tám online template

1. Chuyển từng template theo thứ tự P1 → B4 → B5 → B6 → G1.
2. So sánh context options, selector on/off, max repairs/candidates với preset gốc.
3. Mỗi LLM call phải là node LLM riêng trên graph; không giấu trong context node.
4. Giữ chế độ `sql_only` cho benchmark; thêm chế độ `answer` cho người dùng, thể hiện phần cuối thật trên graph.
5. Chế độ answer: chọn SQL → dùng observation thành công của chính SQL/dataset revision đó hoặc thực thi nếu chưa có → trả bảng → LLM diễn giải → Output.
6. Không trả lời từ SQL lỗi. Với empty result trả rõ không có dòng; với truncated thông báo giới hạn. Không coi chạy thành công đồng nghĩa đúng nghiệp vụ.
7. Sửa invalid candidate ID fallback sang ranking hợp lệ; ưu tiên ứng viên thực thi thành công khi có. Gắn observation bằng candidate ID.

**Xong khi:** tám template còn đúng biến thể; B6 loop và G1 nhiều ứng viên được test; chế độ answer có dữ liệu thực thi và câu trả lời, sql_only vẫn dùng được cho eval.

### M4 — Offline và registry dataset thống nhất

1. Tạo service dataset dùng chung cho UI, CLI importer và online. Giữ tương thích CLI hiện có qua adapter.
2. Upload SQLite + tài liệu vào vùng staging. Validate tên, định dạng và schema; không dùng filename client làm đường dẫn ghi tùy ý.
3. Lưu trạng thái failed/interrupted ngay cả khi chưa index thành công; không chỉ có manifest sau success như importer hiện tại.
4. Tạo offline template từ từng adapter. Đọc dependency thực tế của hàm cũ; schema/event và GraphRAG là nhánh riêng, không nối tuần tự tùy ý.
5. Mỗi node nhận setting snapshot của run. Sửa tình trạng importer ép graph disabled chỉ bằng cách bổ sung lựa chọn rõ ràng; giữ mặc định cũ.
6. Fingerprint source + config liên quan + upstream artifact. Chỉ reuse khi fingerprint khớp. Chunk đổi làm embed/index stale; prompt trả lời đổi không làm index stale.
7. Resume phải kiểm tra artifact và dependency, không chỉ dựa vào dấu tick cũ. Khóa ghi cùng collection để tránh hai job local Qdrant xung đột.
8. Dataset version có capabilities (schema/business/index/event/graph), trạng thái và lỗi. Pipeline kiểm tra capability mình cần.
9. Chỉ công bố index ready khi ghi/kiểm tra thành công; run lỗi không phá phiên bản ready trước đó.
10. Sau register, online lấy được cùng dataset ID/revision ngay. Không cần sửa file tay hoặc đọc bundle benchmark.

**Xong khi:** import mới bằng API → offline thật → list online thấy dataset → truy vấn đúng DB. Resume không embed lại bước còn hợp lệ; thay input làm downstream stale đúng.

### M5 — API thống nhất và job/event thật

Tạo router mới hoặc mở rộng Studio, tránh xung đột `/datasets` benchmark cũ. Đề nghị contract:

| Endpoint | Trách nhiệm |
|---|---|
| `GET /studio/node-types` | Registry và config/input/output schemas |
| `GET/POST /studio/workflows` | List/tạo bản người dùng |
| `GET/PUT /studio/workflows/{id}` | Đọc/lưu revision, validate |
| `POST /studio/runs` | Chạy revision đã lưu, trả run ID |
| `GET /studio/runs/{id}` | Snapshot, trạng thái, output |
| `GET /studio/runs/{id}/events` | Stream sự kiện có sequence để nối lại |
| `POST /studio/runs/{id}/cancel` | Yêu cầu dừng tại điểm an toàn |
| `POST /studio/workflows/{id}/nodes/{node_id}/test` | Chạy node với input kiểm thử |
| `POST/GET /studio/datasets` | Upload/đăng ký và list dataset người dùng |
| `GET /studio/datasets/{id}` | Revision/capabilities/artifacts |

Chốt request/response bằng Pydantic và tests trước viết UI. Job cần chạy qua nhiều request mà không phụ thuộc tab còn mở. Có thể dùng worker trong tiến trình và kho metadata local; không thêm Celery/Redis khi chưa cần. Hạn chế ghi offline đồng thời trên cùng tài nguyên.

Event tối thiểu: run/node started, progress khi đo được, node completed/failed, run completed/failed/cancelled/interrupted. Mỗi event có run ID, node ID/invocation ID nếu có, sequence, timestamp. Không tạo phần trăm giả. Cancel không được hứa ngắt tức thì một GPU/API call không hỗ trợ cancel.

**Xong khi:** đóng/mở UI vẫn xem job đúng; kết nối lại không nhân đôi trace; backend error làm UI failed; không có trạng thái success do frontend suy đoán.

### M6 — UI offline/online dùng chung

1. Giữ một shell/sidebar: Dữ liệu, Pipeline offline, Pipeline online, Lịch sử, Settings.
2. Chỉ mở canvas khi chọn/tạo pipeline; danh sách dữ liệu và settings không hiện graph.
3. Tách JS/CSS hiện tại thành module theo trách nhiệm. Chọn thư viện graph editor sau kiểm tra stack repo; nếu thêm frontend build phải có asset và hướng dẫn build rõ cho fresh clone, không phụ thuộc CDN lúc runtime.
4. Canvas lấy nodes/edges từ definition backend; thư viện node lấy từ registry. Hỗ trợ thêm, nối, đổi vị trí, xóa, nhân bản node; validate trước save/run.
5. Inspector có tab Cấu hình, Input, Output, Lần chạy. LLM có prompt editor, chọn biến, model, JSON schema, preview và test.
6. Nút Lưu gọi API; dirty state rõ. Chạy khi có thay đổi chưa lưu phải save revision thành công trước hoặc yêu cầu người dùng chọn rõ, không âm thầm chạy bản cũ.
7. Offline: form upload → chọn template → cấu hình node → Run → xem artifacts/status → nút Dùng để hỏi chuyển sang online với đúng dataset revision.
8. Online: chọn dataset → pipeline → question → Run → answer/SQL/result table; có hiển thị error/empty/truncated.
9. Settings đưa toàn bộ field từ inventory M0 vào UI dạng nhóm; có Raw JSON nâng cao trong cùng shell. Hiển thị giá trị hiệu lực và nguồn kế thừa tại node; không chỉ lưu mà consumer vẫn dùng preset cũ.
10. Bỏ iframe và link bắt buộc sang Gradio khỏi luồng chính. Có thể giữ `/ui` tương thích tạm, nhưng tính năng cần thiết không được chỉ tồn tại ở đó.
11. Giữ quyền truy cập các công cụ artifact/graph/eval/chat cũ trong cùng shell nếu chúng đang được dùng; không gọi việc bỏ tính năng là thống nhất UI.

**Xong khi:** mọi thao tác chính có request thật; reload còn cấu hình; offline và online dùng cùng dataset; người dùng hoàn thành luồng mà không mở `/ui`.

### M7 — Tài liệu và bàn giao

1. Cập nhật README root và MVP: cài đặt mới, env, CPU/GPU, frontend nếu có, upload, offline, prompt, online, version/resume, troubleshooting.
2. Có demo tạo SQLite nhỏ và business.md thật, giải thích rõ file ví dụ. Không cần source runtime hoặc eval history.
3. Kiểm thử fresh clone/code-only và luồng browser mục 9.
4. Báo file thay đổi, test kết quả, phần chưa đạt và cách tự chạy. Không gọi “hoàn tất” nếu còn acceptance bắt buộc thiếu.
5. Dừng server/worker do agent mở, xác nhận tiến trình kiểm thử kết thúc; không kill tất cả Python trên máy.

## 7. Cách làm việc cho agent

- Mỗi lần chỉ thực hiện một mốc hoặc một phần nhỏ của mốc. Đọc consumer trước đổi contract.
- Trước code, viết ngắn: phần đang làm, hành vi đầu vào/đầu ra, test sẽ chứng minh gì.
- Sau code, chạy test liên quan và kiểm tra diff. Không thay assertion để che regression chưa hiểu.
- Nếu phát hiện code khác mô tả: ghi bằng chứng, điều chỉnh chi tiết triển khai nhưng không giảm mục tiêu hoặc bỏ tính năng.
- Không hỏi lại các lựa chọn thường quy đã chốt ở đây. Chỉ hỏi khi có yêu cầu thực sự mâu thuẫn hoặc thiếu thông tin không thể suy ra.
- Nếu thiếu quyền/network/dependency, tiếp tục phần độc lập và báo đúng blocker; không dùng mock để tuyên bố integration đã chạy thật.
- Nếu phải bàn giao giữa chừng, ghi mốc xong, file đã sửa, test đã chạy, failure còn lại, bước tiếp theo. Tài liệu kế hoạch không tự động là bằng chứng hoàn thành.

## 8. Những lỗi triển khai phải tự kiểm tra

- Có nhiều file gọi model gần giống nhau cho mỗi scenario? Chưa đạt shared LLM node.
- Inspector sửa prompt nhưng payload không có revision/config? Chưa đạt.
- Backend nhận config nhưng closure vẫn load settings cũ? Chưa đạt.
- Canvas được tạo từ danh sách tên cố định khác graph thực thi? Chưa đạt.
- Offline báo completed nhưng dataset online chưa dùng được? Chưa đạt.
- GraphRAG enabled trên UI nhưng service luôn ép false? Chưa đạt.
- Một node ID chạy ba lần nhưng UI/state chỉ giữ lần cuối? Chưa đạt trace loop.
- Lưu index metadata trước khi index thành công? Chưa đạt tính nhất quán.
- Trả lời LLM chỉ từ câu hỏi/context, chưa nhận SQL result? Chưa đạt end-to-end.
- Mọi pipeline có class riêng nhưng chỉ gọi chung helper? Chưa đạt tái sử dụng ở tầng node.
- Node chuyên biệt vẫn gọi LLM ẩn bên trong? Phải tách call thành instance LLM nếu nằm trong workflow tương tác.

## 9. Kiểm thử bắt buộc và bằng chứng

Chạy từ root repo. Baseline hiện có, dùng thư mục temp mới mỗi lần để tránh pytest xóa thư mục cũ:

```powershell
$taskTemp = Join-Path '.test-tmp' ('workflow-' + [guid]::NewGuid().ToString('N'))
.\.venv\Scripts\python.exe -m pytest src/branch_sql_MVP/tests/test_text2sql_benchmark.py src/branch_sql_MVP/tests/test_studio.py src/branch_sql_MVP/tests/test_fresh_setup.py -q -p no:cacheprovider --basetemp=$taskTemp
```

Không test paid LLM trong regression. Dùng fake adapter và SQLite thật để kiểm tra plumbing; ghi rõ đó là mocked LLM. Integration embedding/index dùng model thật đã có nếu khả dụng; nếu không, báo chưa xác minh, không tuyên bố toàn bộ retrieval hoạt động thật.

| Nhóm | Case phải chứng minh |
|---|---|
| Contracts | Duplicate ID, reference sai/thiếu, type sai, cycle không bound bị từ chối |
| Shared nodes | Hai instance cùng executor nhưng config/output độc lập; cùng type chạy ở hai pipeline |
| LLM | Prompt/model đúng từng instance; resolve biến; schema sai; API key không vào lưu trữ/trace |
| Branch/state | Chỉ nhánh được chọn chạy; merge không deadlock; fan-out không mất output; loop giữ từng lần |
| SQL | SELECT/CTE thật; chặn write; timeout; empty; truncated; chọn đúng observation; không trả lời từ error |
| Compatibility | Tám preset bảo toàn selector/event/repair/candidate settings và sql_only |
| Offline | Upload mới; failure có trạng thái; fingerprint/resume; stale downstream; index ready đúng lúc |
| Persistence | Save/reload workflow và dataset; revision conflict; restart đánh dấu interrupted |
| Fresh setup | Không `.env` thật/dev/test/bundle/eval history vẫn mở app, import demo và chạy được |

Browser acceptance bắt buộc, dùng browser automation nếu khả dụng:

1. Mở root app; không có iframe trong luồng chính, chưa chọn pipeline không có canvas.
2. Upload demo SQLite có orders 100000 và 250000 cùng business.md tổng doanh thu.
3. Chạy offline schema-only; thấy các sự kiện/backend artifacts thật và dataset dùng được P1.
4. Chạy phiên bản có index; online hiển thị capability mới chỉ sau success.
5. Tạo bản sao pipeline, thêm/cấu hình LLM instance, chọn biến, save, reload; config không mất.
6. Dùng fake adapter để kiểm tra deterministic; câu SUM trả SQL result 350000 và answer dựa trên result.
7. Đổi prompt và kiểm tra request/model input thật đã đổi; không chỉ quan sát textbox.
8. Thử lỗi node, reconnect, cancel; UI thể hiện đúng trạng thái backend.
9. Xem hai LLM instance hoặc loop: chọn từng invocation thấy đúng input/output riêng.
10. Xác nhận settings cơ bản và nâng cao đều truy cập được trong shell mới.

## 10. Mẫu báo cáo tiến độ / hoàn thành

```text
Mốc: Mx — tên
Đã triển khai: hành vi cụ thể, file chính.
Bằng chứng: lệnh test + kết quả; thao tác UI/API + kết quả.
Chưa đạt: acceptance còn thiếu, lý do cụ thể.
Mốc tiếp theo: bước nhỏ tiếp theo, dependency.
Server/worker: đang chạy để kiểm tra hay đã dừng.
```

Chỉ kết luận hoàn thành toàn nhiệm vụ khi M0–M7 và các acceptance bắt buộc đều đạt. Một demo đẹp, một test P1 pass hoặc một endpoint trả 200 không đủ.

## 11. Nguồn tham khảo thiết kế

- [Dify Workflow: node có input/output và điều phối](https://dify.ai/blog/dify-ai-workflow)
- [Dify quick start: node và kiểm tra từng bước](https://docs.dify.ai/en/guides/application-orchestrate/creating-an-application)
- [SAG: tham khảo giao diện theo yêu cầu người dùng](https://github.com/Zleap-AI/SAG)

Nếu sử dụng trực tiếp code hoặc asset bên ngoài, kiểm tra license và giữ attribution phù hợp. Tài liệu này không yêu cầu sao chép code từ các dự án tham khảo.

# SQL Studio — kb-text2sql tích hợp

Toàn bộ 62 file nguồn, các notebook, tests, script dịch, settings và dữ liệu từ
`C:\Users\Khanh\Documents\kb-text2sql` đã được chuyển vào nhánh này.
`settings.json` giữ nguyên nội dung nguồn. `.env` được chép cục bộ, không đưa vào Git.

## Chạy app

Từ thư mục gốc `vi-coze`:

```powershell
uv sync --extra api --extra llm
uv run --extra api --extra llm python -m src.branch_sql_MVP.app.app
```

Mở http://127.0.0.1:8000. Giao diện công cụ/setting đầy đủ vẫn ở `/ui`.
Chọn một trong 8 pipeline để mở đồ thị. “Xem lần chạy đã lưu” đọc kết quả benchmark
đã sao chép, không gọi model. “Chạy thử” thực thi workflow với cấu hình tối ưu,
stream trạng thái và đầu ra node; API key nhập trên UI chỉ dùng cho lần chạy đó.
Chỉnh câu hỏi sẽ bỏ evidence và difficulty của câu mẫu để tránh dùng nhầm metadata.

## Dữ liệu và cấu hình tối ưu

- `data/dev`, `data/test`: toàn bộ 175 file dữ liệu nguồn, gồm SQLite và tài liệu.
- `.runtime`: index, artifact, ledger và các run tối ưu; bỏ cache uv và thư mục test tạm.
- `.runtime/luna_test_optimization_20260908/bundle.json`: 8 cấu hình được chọn,
  gồm context/retrieval, generation, route và repair bound.
- `.runtime/luna_internal_holdout_v1/qdrant`: index dùng bởi lần tối ưu đã chọn.
- `upstream`: README, PLAN, AGENT, dependency lock, Docker và báo cáo nguyên bản.
- `upstream/migration.json`: nguồn gốc và checksum code nguồn trước điều chỉnh import/path.
- `.test-tmp/mvp-migration/original` ở gốc workspace: bản sao nhánh MVP trước tích hợp.

Dataset, `.runtime` và `.env` tồn tại đầy đủ trên máy nhưng được loại khỏi Git.
Đường dẫn tuyệt đối trong artifact được chuyển sang vị trí mới. Fingerprint và
metric lịch sử giữ nguyên để ghi nhận lần chạy gốc; không coi chúng là benchmark mới.
Các kết quả tối ưu là **test-tuned/in-sample**, không phải holdout độc lập.

Settings thông thường được lưu ở `settings.json`; tham số benchmark riêng nằm trong
bundle và được hiển thị ở từng pipeline. Thay settings thông thường không viết lại
các cấu hình benchmark đã chọn.

## Kiểm chứng tích hợp

45 tests passed: 29 test nguồn, 13 test MVP hiện có và 3 test tích hợp Studio.
Streaming được kiểm tra bằng LangGraph thật với model giả, gồm nhánh lỗi và cô lập
state giữa các lần chạy; không chạy lại benchmark hoặc gọi model trả phí.
Test `tests/test_llm_registry.py` của nhánh SQL khác không thu thập được do thiếu
module `src.branch_sql.online.llm.registry` có sẵn ngoài phạm vi tích hợp.

UI tham khảo cách tổ chức canvas/node/trace của [Dify](https://www.dify.ai/workflows)
và workspace knowledge của [SAG](https://github.com/Zleap-AI/SAG).

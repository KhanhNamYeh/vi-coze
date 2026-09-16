# Báo cáo kiểm tra MVP — 2026-09-10

Người dùng đã yêu cầu ưu tiên MVP, làm nhanh và hạn chế test. Không coi tài liệu này là xác nhận toàn bộ nghiệm thu M0–M7 đã hoàn tất.

## Đã triển khai

- Tám preset dùng compiler LangGraph chung; builder cũ là adapter tương thích.
- Một executor LLM cho generate/repair/selector/router/answer và các LLM GraphRAG; prompt/model theo từng instance.
- Schema linking, value linking, retrieval, example retrieval và ghép context có node riêng dùng thuật toán cũ. Có test so sánh đầu ra với context builder cũ.
- Bounded loop, fan-out/collect, nhánh loại trừ; invocation ID độc lập và trace scope lồng nhau. Repair có dừng khi SQL lặp.
- Answer mode chạy SQLite read-only, chặn trả lời từ SQL lỗi, trả SQL/bảng/answer. Observation có candidate_id và giới hạn số dòng hiển thị.
- Workflow lưu revision atomically; run đóng băng definition/settings và lưu event trong SQLite, có reconnect/cancel/interrupted.
- Offline upload và CLI dùng cùng stage adapters. Cache kiểm tra nguồn/config/checksum; từ chối nguồn thay đổi trong cùng dataset; không ghi đè dataset ready.
- Collection index theo fingerprint; không xóa/tạo lại collection cũ. Chỉ công bố ready sau kiểm tra collection và số point.
- Editor chung offline/online: add/move/duplicate/delete/connect, prompt/model, mapping biến, preview/test riêng cả node trong loop, tab Cấu hình/Input/Output/Lần chạy, Settings và công cụ API cũ.
- README hướng dẫn clone mới, env, CPU/GPU, demo, upload, prompt, resume và cấu hình chunk cho tài liệu mới.

## Bằng chứng đã có

- Full regression: **58 passed**, lệnh `python -m pytest src/branch_sql_MVP/tests -q -p no:cacheprovider --basetemp=.test-tmp/continue-20260910-g`.
- Các test LLM dùng provider giả; SQLite thật, không gọi Gemini trả phí.
- Browser: trang đầu không hiện canvas; sửa prompt → chuyển node → lưu revision 2 → reload giữ nguyên prompt.
- Browser: upload SQLite demo 100000 + 250000 và business.md → chạy offline schema-only → completed, 15 event thật → dataset `ui_demo_20260910` xuất hiện ở online.
- Integration CPU: model AITeamVN/Vietnamese_Embedding thật + BM25 + Qdrant local chạy qua chunk/embed/index/register thành công trong `.test-tmp/real-index-20260910`. Graph tắt. Demo nhỏ dùng heading_level=1, child_min=1.
- Index integration nói trên chạy trước thay đổi cuối về collection theo fingerprint; chưa chạy lại integration này. Kiểm tra đầy đủ resume embedding thật chưa hoàn tất.
- JavaScript đã kiểm tra cú pháp bằng `node --check`.

## Chưa nghiệm thu đầy đủ

- Validation kiểu/reference/nhánh ở mức mọi cấu hình tùy ý và schema metadata của toàn bộ node chưa đầy đủ như Dify.
- GraphRAG cache/resume từng LLM extraction/report, artifact lớn trong state và toàn bộ integration GraphRAG còn cần hoàn thiện.
- Browser end-to-end answer 350000, index có capability mới, lỗi/reconnect/cancel và chọn invocation chưa chạy đủ mọi case. Backend đã có test cho các hành vi chính.
- Chưa đánh giá độ đúng nghiệp vụ của Gemini trên dữ liệu mới; chạy SQL thành công không chứng minh SQL đúng nghiệp vụ.
- Chỉ hỗ trợ một tiến trình app dùng kho local. Không triển khai worker đa tiến trình.

Đây là bản MVP có luồng sử dụng thật, không phải tuyên bố hoàn tất mọi tiêu chí M0–M7. Phần còn lại được giữ rõ để không mở rộng phạm vi trong lượt ưu tiên tốc độ.

Kiểm tra cuối theo phạm vi MVP: 7 test fresh setup/template đạt; JavaScript syntax check đạt. Không chạy thêm integration sau yêu cầu hạn chế test.

MVP cơ bản bổ sung: form provider/model/CPU-CUDA; chặn gửi trùng khi bấm Chạy; bỏ theo dõi run cũ khi đổi workflow; đồng bộ cấu hình LLM JSON với ô prompt/model; xử lý tên dataset dài. Kiểm tra cuối: 7/7 fresh setup/template đạt, JS syntax đạt, tên dataset 64 ký tự hợp lệ. Không khởi động thêm server; cổng 8012 không có listener.

2026-09-11 — Điều chỉnh theo yêu cầu người dùng: ưu tiên demo pipeline có sẵn, bỏ UI tạo/xóa/nhân bản/nối/kéo node và workflow trống. Giữ chọn dataset, setting/prompt, Chạy toàn pipeline, Debug node và input/output từng invocation. Debug lấy được input thật và settings snapshot của run đã chọn. README đã thay hướng dẫn dựng node bằng hướng dẫn chạy/debug. Kiểm tra tối thiểu: JS syntax, đối chiếu control HTML/JS, test API debug node lồng nhau đạt. Không mở server kiểm thử.

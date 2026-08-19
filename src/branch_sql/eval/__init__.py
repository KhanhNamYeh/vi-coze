"""Đo độ chính xác của nhánh SQL.

    gold_parse.py       testcase.xlsx -> dev.json / test.json / fewshot.chunks.json
    gold.py             testcase.json + gold_sample -> đối tượng có kiểu
    metrics.py          hàm thuần, không I/O - chỗ định nghĩa chỉ số
    retrieval_eval.py   chạy truy hồi thật rồi cộng dồn chỉ số

Ba tập, ba vai trò:

    data/eval/sql/dev.json                18 câu hỏi, chỉnh tham số, lặp thoải mái
    data/eval/sql/test.json               15 câu hỏi, báo cáo cuối
    data/processed/sql/fewshot.chunks.json  18 ví dụ đem đi index - CÙNG 18 dòng với dev

Ba cấu hình truy hồi được đo tách nhau, vì chúng trả lời ba câu hỏi khác nhau:

    docs     chỉ chunk schema   -> tìm đủ bảng để viết được câu SQL chưa?
    fewshot  chỉ chunk ví dụ    -> có lấy được ví dụ giống việc không?
    both     trộn cả hai        -> ví dụ có chiếm mất chỗ của bảng không?

`dev` chỉ đo được setup `docs`, vì nó trùng dữ liệu với `fewshot` đang nằm trong
chỉ mục. `assert_no_leak` trong `gold.py` chặn việc này.
"""

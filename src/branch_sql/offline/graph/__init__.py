"""Chặng `graph` — knowledge graph, có gọi LLM.

    knowledge_graph.py  markdown -> node-link JSON + HTML  (prototype)

Tách khỏi `link/` vì hai chặng khác hẳn bản chất, không phải vì kích thước:

    link    tất định. Cùng đầu vào cho ra cùng đầu ra, chạy lại được vô hạn lần,
            không cần mạng, không tốn tiền. Chỉ dùng cấu trúc mà `extract` đã có.
    graph   gọi LLM. Kết quả phụ thuộc model, nhiệt độ và lần chạy; cần một
            endpoint đang sống; và có thể bịa ra thực thể không có trong tài liệu.

Trộn hai thứ vào cùng thư mục thì không nói được câu "phần này kiểm chứng được
bằng cách chạy lại" cho bất kỳ phần nào. ĐÂY LÀ CHẶNG DUY NHẤT trong nhánh SQL
được phép gọi LLM.

Trạng thái: prototype, chưa nằm trong `offline/pipeline.py`. Hiện đọc thẳng `.md`
và tự tách lại bảng bằng regex, tức làm lại việc mà `extract` và `link` đã làm
bằng một bộ luật thứ hai. Nên chuyển sang đọc `<doc_id>.linked.json`.
"""

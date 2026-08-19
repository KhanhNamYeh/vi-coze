"""Chặng `api` — Knowledge Studio, điều khiển pipeline offline từ trình duyệt.

    store.py    SQLite: project, knowledge, run
    queue.py    hàng đợi một luồng, chạy CLI qua subprocess
    app.py      FastAPI: REST + phục vụ static/index.html

Ranh giới quan trọng nhất: UI KHÔNG ghi vào `config/sql.json`. Profile được
validate như một khối nên một knowledge sai làm cả hai dự án cùng không nạp được.
Trạng thái do UI tạo nằm ở `data/api.db`; lúc chạy job, `queue.py` sinh một profile
tạm từ mặc định cộng bản chụp của knowledge.

Chặng này không import gì từ `offline/` ngoài `doc_parse.doc_id_of`. Pipeline chạy
qua subprocess để CLI vẫn là nguồn sự thật duy nhất, và để đổi dự án được - config
nạp lúc import nên một tiến trình chỉ phục vụ được một dự án.
"""

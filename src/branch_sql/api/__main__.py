"""Điểm vào: `uv run --extra api python -m src.branch_sql.api`

Bind 127.0.0.1: server này ghi file và chạy subprocess theo lệnh từ trình duyệt,
chưa có xác thực nên không được mở ra mạng.
"""

import uvicorn

if __name__ == "__main__":
    uvicorn.run("src.branch_sql.api.app:app", host="127.0.0.1", port=8000, reload=False)

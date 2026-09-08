"""Sổ token bền vững cho một tiến trình benchmark, kể cả lời gọi lỗi."""

from __future__ import annotations

import json
from pathlib import Path
from threading import Lock


class TokenBudgetExceeded(RuntimeError):
    """Dừng run có thể resume, không chấm thành SQL sai."""


class TokenBudget:
    def __init__(self, path: Path, limit: int):
        self.path, self.limit, self.lock = path, limit, Lock()
        self.used = sum(json.loads(line)["delta"] for line in path.read_text(encoding="utf-8").splitlines()) if path.exists() else 0

    def _record(self, delta: int, **details) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps({"delta": delta, **details}) + "\n")
        self.used += delta

    def reserve(self, maximum: int) -> int:
        with self.lock:
            if self.used + maximum > self.limit:
                raise TokenBudgetExceeded(f"Dừng trước trần {self.limit:,} token; đã dùng/giữ chỗ {self.used:,}")
            self._record(maximum, event="reserve")
        return maximum

    def settle(self, reserved: int, usage: dict) -> None:
        actual = int(usage.get("input_tokens", 0)) + int(usage.get("output_tokens", 0))
        if actual <= 0:
            return  # Không rõ usage: giữ nguyên dự phòng, không giả định miễn phí.
        with self.lock:
            self._record(actual - reserved, event="settle", usage=usage)


active_budget: TokenBudget | None = None

"""Kiểm chứng static/index.html — cú pháp và các mối nối tới API.

Lý do có file này: giao diện là một khối `<script>` duy nhất, nên MỘT lỗi cú pháp
làm cả khối không parse được. Triệu chứng rất dễ đọc nhầm - layout tĩnh vẫn hiện
nguyên vẹn, chỉ mất chữ do JS ghi vào và mọi nút bấm im lặng. Nhìn qua tưởng CSS
hỏng. Đã xảy ra thật một lần, do một phép thay chuỗi làm rơi dấu thoát và tạo ra
chuỗi chưa đóng.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

UI = Path(__file__).resolve().parents[1] / "src" / "branch_sql" / "api" / "static" / "index.html"


@pytest.fixture(scope="module")
def html() -> str:
    return UI.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def script(html: str) -> str:
    return html[html.index("<script>") + len("<script>") : html.rindex("</script>")]


class TestCuPhap:
    @pytest.mark.skipif(not shutil.which("node"), reason="cần node để kiểm cú pháp JS")
    def test_script_parse_duoc(self, script, tmp_path):
        js = tmp_path / "ui.js"
        js.write_text(script, encoding="utf-8")
        r = subprocess.run(["node", "--check", str(js)], capture_output=True, text=True)
        assert r.returncode == 0, f"lỗi cú pháp JS:\n{r.stderr}"

    def test_khong_co_chuoi_chua_dong(self, script):
        """Chuỗi mở bằng nháy đơn mà không đóng trên cùng dòng - đúng kiểu hỏng
        mà một phép thay chuỗi làm rơi dấu thoát gây ra."""
        broken = [
            l.strip() for l in script.splitlines()
            if l.rstrip().endswith(("split('", "join('", "= '", "+ '"))
        ]
        assert not broken, f"chuỗi chưa đóng: {broken[:3]}"


class TestNoiVaoAPI:
    def test_co_cau_noi_api(self, script):
        for probe in ("const API =", "API.projects", "API.startRun", "API.runs"):
            assert probe in script, f"thiếu {probe}"

    def test_khong_con_du_lieu_mo_phong(self, script):
        """`seed()` dựng dự án giả trong localStorage. Còn gọi nó nghĩa là UI
        vẫn đọc dữ liệu bịa thay vì hỏi server."""
        assert "\n  seed();" not in script
        assert "async function loadState()" in script

    def test_sau_chang_khop_pipeline(self, script):
        m = re.search(r"PL\.stageOrder = \[(.*?)\]", script)
        assert m, "không thấy PL.stageOrder"
        stages = re.findall(r"'([a-z_]+)'", m.group(1))
        assert stages == ["parse", "extract", "link", "chunk", "embed", "index"]

    def test_panel_chang_dung_so_lieu_that(self, script):
        assert "function statPanel(" in script
        assert "/stats" in script

    def test_tab_logs_doc_tu_api(self, script):
        assert "async function renderLogsTab()" in script
        assert "artifacts" in script


class TestFormChunk:
    def test_form_sinh_dung_hinh_dang_chunkcfg(self, script):
        for key in ("split_on", "on_overflow", "on_underflow", "overlap_rows",
                    "child_roles", "repeat_header"):
            assert key in script, f"form thiếu {key}"

    def test_dau_ngan_doi_thanh_ky_tu_that(self, script):
        r"""Form nhập `\n` dạng VĂN BẢN (hai ký tự). Không đổi thành ký tự thật
        thì splitter đi tìm đúng chuỗi hai ký tự đó và gần như không khớp."""
        assert "String.fromCharCode(92, 92)" in script, (
            "regex đổi ký tự thoát phải khớp dấu gạch chéo literal, cần HAI backslash"
        )

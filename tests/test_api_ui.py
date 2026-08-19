"""Kiểm chứng static/index.html — cú pháp và các mối nối tới API.

Lý do có file này: giao diện là một khối `<script>` duy nhất, nên MỘT lỗi cú pháp
làm cả khối không parse được. Triệu chứng rất dễ đọc nhầm - layout tĩnh vẫn hiện
nguyên vẹn, chỉ mất chữ do JS ghi vào và mọi nút bấm im lặng. Nhìn qua tưởng CSS
hỏng. Đã xảy ra thật một lần, do một phép thay chuỗi làm rơi dấu thoát và tạo ra
chuỗi chưa đóng.
"""

from __future__ import annotations

import os
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


class TestDungThat:
    """Dựng trang trong DOM thật rồi bấm qua tới form.

    Kiểm cú pháp thôi chưa đủ: lỗi runtime (biến của mô hình form cũ) vẫn làm
    overlay mở ra trống trơn mà không báo gì. Đã xảy ra thật - `renderSettingForm`
    đọc `f.files` sau khi trường đó bị bỏ khỏi DEFAULT_FORM.
    """

    @pytest.mark.skipif(not shutil.which("node"), reason="cần node")
    def test_form_knowledge_dung_duoc_noi_dung(self, tmp_path):
        harness = tmp_path / "run.js"
        harness.write_text(HARNESS.replace("__UI__", UI.as_posix()), encoding="utf-8")
        # node tìm module theo vị trí SCRIPT chứ không theo cwd, mà harness nằm
        # ở thư mục tạm - phải chỉ đường tới node_modules bằng NODE_PATH.
        env = {**os.environ, "NODE_PATH": str(UI.parent / "node_modules")}
        r = subprocess.run(["node", str(harness)], capture_output=True, text=True,
                           cwd=UI.parent, timeout=180, env=env)
        if "Cannot find module 'jsdom'" in r.stderr:
            pytest.skip("chưa cài jsdom: npm i --no-save jsdom")
        assert r.returncode == 0, r.stderr[-1500:]
        out = r.stdout
        assert "FORM_OK" in out, "form không dựng được: " + out + r.stderr[-800:]
        assert "NO_ERROR" in out, "có lỗi runtime: " + out


HARNESS = """
const { JSDOM } = require('jsdom');
const fs = require('fs');
const errors = [];
const dom = new JSDOM(fs.readFileSync('__UI__', 'utf8'), {
  runScripts: 'dangerously', pretendToBeVisual: true,
  beforeParse(w){
    w.fetch = async (u) => {
      const map = {
        '/api/projects': [{id:1,name:'P1',description:'',knowledge:[
          {id:'k1',source:'a.docx',project:1,collection:'c',chunk:{mode:'general'},origin:'profile'}]}],
        '/api/sources': [{name:'a.docx',size:10,supported:true}],
      };
      const key = Object.keys(map).find(k => u.startsWith(k));
      return { ok: !!key, headers: {get: () => 'application/json'},
               json: async () => map[key] || [], text: async () => JSON.stringify(map[key] || []) };
    };
    w.addEventListener('error', e => errors.push(String(e.error && e.error.stack || e.message)));
    w.addEventListener('unhandledrejection', e => errors.push(String(e.reason)));
  }});

setTimeout(() => {
  const w = dom.window, d = w.document;
  const pj = d.querySelector('[data-open-pj]');
  if (pj) pj.dispatchEvent(new w.MouseEvent('click', {bubbles: true}));
  setTimeout(() => {
    const b = d.getElementById('btn-open-setting') || d.getElementById('btn-open-setting2');
    if (b) b.dispatchEvent(new w.MouseEvent('click', {bubbles: true}));
    setTimeout(() => {
      const form = d.getElementById('set-form');
      const secs = d.querySelectorAll('#set-form .f-num').length;
      if (form && form.innerHTML.length > 2000 && secs >= 4) console.log('FORM_OK', secs);
      else console.log('FORM_TRONG', form ? form.innerHTML.length : 'khong co', secs);
      console.log(errors.length ? 'ERRORS ' + errors.slice(0,2).join(' ~~ ') : 'NO_ERROR');
      process.exit(0);
    }, 300);
  }, 400);
}, 900);
"""


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

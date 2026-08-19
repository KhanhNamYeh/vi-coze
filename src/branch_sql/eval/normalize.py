"""Chuẩn hoá định danh của nhánh SQL.

Tên bảng xuất hiện ở hai nơi với hai cách viết khác nhau: tài liệu schema ghi cả
biểu thức gọi hàm kèm tham số, còn file testcase ghi rút gọn. So khớp thô sẽ
trượt đúng ở các table function. Mọi phép đối chiếu bảng phải đi qua `table_key`.
"""

from __future__ import annotations

import re

# TABLE(pck_report_chatbox.get_rev_data_by_precinct (TO_DATE(...), UPPER(:user_name)))
# TABLE(pck_report_chatbox.get_rev_data_by_precinct)
# -> get_rev_data_by_precinct
TABLE_FN = re.compile(r"TABLE\s*\(\s*(?:\w+\.)*(\w+)", re.IGNORECASE)


def table_key(name: str | None) -> str:
    """Tên bảng ở bất kỳ cách viết nào -> khoá đối chiếu duy nhất, chữ thường."""
    if not name:
        return ""
    name = name.strip()
    if m := TABLE_FN.match(name):
        return m.group(1).lower()
    return name.lower()

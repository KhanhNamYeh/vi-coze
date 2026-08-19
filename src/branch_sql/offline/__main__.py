"""Điểm vào cho `python -m src.branch_sql.offline`.

Chạy trọn một DỰ ÁN, không phải một file: bộ tri thức nào thuộc dự án nào khai ở
`knowledge[]` trong profile.
"""

import sys

from .project import main

raise SystemExit(main(sys.argv[1:]))

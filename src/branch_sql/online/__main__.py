"""Điểm vào cho `python -m src.branch_sql.online`."""

import sys

from .pipeline import main

raise SystemExit(main(sys.argv[1:]))

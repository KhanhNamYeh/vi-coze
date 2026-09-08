"""Tạo SQLite nhỏ từ dữ liệu giả; không cần dataset BIRD hoặc API key."""
from pathlib import Path
import sqlite3


def main():
    import sys
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    target = Path(__file__).resolve().parents[1] / '.runtime/demo.sqlite'
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        print(f'Đã có demo: {target}')
        return
    with sqlite3.connect(target) as db:
        db.execute('CREATE TABLE orders (id INTEGER PRIMARY KEY, customer TEXT, amount REAL)')
        db.executemany('INSERT INTO orders VALUES (?, ?, ?)', [(1, 'An', 100000), (2, 'Binh', 250000)])
    print(target)


if __name__ == '__main__':
    main()

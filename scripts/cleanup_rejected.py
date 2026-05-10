#!/usr/bin/env python3
"""删除驳回图片的文件和数据库记录，释放磁盘空间。"""
import sqlite3
from pathlib import Path

DB = Path(__file__).parent.parent / "backend" / "data" / "lumine.db"
OUT = Path(__file__).parent.parent / "output" / "cf-pages"

conn = sqlite3.connect(str(DB))
rows = conn.execute(
    "SELECT slug, path, thumbnail_path FROM images WHERE status='rejected'"
).fetchall()

if not rows:
    print("没有驳回图片")
    conn.close()
    exit()

deleted = freed = 0
for slug, path, thumb in rows:
    for p in (path, thumb):
        if p:
            fp = OUT / p
            if fp.exists():
                freed += fp.stat().st_size
                fp.unlink()
                deleted += 1
                print(f"  DEL {p}")

conn.execute("DELETE FROM images WHERE status='rejected'")
conn.commit()
conn.close()

print(f"\n删除 {deleted} 个文件，释放 {freed / 1024 / 1024:.1f} MB")

#!/usr/bin/env python3
"""删除驳回图片的文件和数据库记录，释放磁盘空间，同时清理源文件防止重复导入。"""
import sqlite3
import os
from pathlib import Path

ROOT = Path(__file__).parent.parent
DB = ROOT / "backend" / "data" / "lumine.db"
OUT = ROOT / "output" / "cf-pages"

conn = sqlite3.connect(str(DB))
rows = conn.execute(
    "SELECT slug, path, thumbnail_path, game, source_url FROM images WHERE status='rejected'"
).fetchall()

if not rows:
    print("没有驳回图片")
    conn.close()
    exit()

# 收集可能包含源文件的目录
tmp_dirs = set()
for d in ROOT.glob("tmp/*"):
    if d.is_dir():
        tmp_dirs.add(str(d))

deleted = freed = 0
src_deleted = 0

for slug, path, thumb, game, source_url in rows:
    # 删除 cf-pages 输出文件
    for p in (path, thumb):
        if p:
            fp = OUT / p
            if fp.exists():
                freed += fp.stat().st_size
                fp.unlink()
                deleted += 1
                print(f"  DEL {p}")

    # 从 source_url 提取 pixiv ID，删除 tmp/ 中对应的源文件
    if source_url and "pixiv.net/artworks/" in source_url:
        pixiv_id = source_url.rstrip("/").split("/")[-1]
        # 尝试在各 tmp 子目录中查找并删除源文件
        for tmp_dir in tmp_dirs:
            for ext in (".jpg", ".jpeg", ".png", ".webp"):
                src_file = Path(tmp_dir) / f"pixiv_{pixiv_id}{ext}"
                if src_file.exists():
                    src_file.unlink()
                    src_deleted += 1
                    print(f"  DEL {src_file}")
                    freed += src_file.stat().st_size if src_file.exists() else 0
                # 同时删除 JSON 元数据
                json_file = src_file.with_suffix(".json")
                if json_file.exists():
                    json_file.unlink()

conn.execute("DELETE FROM images WHERE status='rejected'")
conn.commit()
conn.close()

print(f"\n删除 cf-pages 文件: {deleted} 个 | 源文件: {src_deleted} 个 | 释放 {freed / 1024 / 1024:.1f} MB")

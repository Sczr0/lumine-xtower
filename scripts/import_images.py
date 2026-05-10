#!/usr/bin/env python3
"""
批量导入图片到 Lumine。

流程:
  原始图片 (PNG/JPG/WebP) → 转 WebP + 缩略图 → cf-pages/ 目录 + SQLite

用法:
    python scripts/import_images.py /path/to/images --game genshin --output-dir output/cf-pages

可选参数:
    --game           游戏名 (genshin/hsr/zzz/honkai3), 默认 genshin
    --source-type    来源类型 (official/manual/submission), 默认 manual
    --status         入库状态, 默认 pending_review
    --db             SQLite 路径, 默认 backend/data/lumine.db
    --output-dir     输出目录, 默认 output/cf-pages
    --thumb-size     缩略图尺寸 WxH, 默认 400x300
    --quality        WebP 质量 (1-100), 默认 85
    --thumb-quality  缩略图质量 (1-100), 默认 75
    --dry-run        只扫描不写入
    --workers        并行进程数, 默认 CPU 核心数
"""

import argparse
import hashlib
import math
import os
import random
import sqlite3
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image, ImageOps

try:
    import blurhash
except ImportError:
    blurhash = None

try:
    import imagehash as ihash
except ImportError:
    ihash = None

try:
    from colorthief import ColorThief
except ImportError:
    ColorThief = None

IMAGE_EXTENSIONS = {".webp", ".png", ".jpg", ".jpeg", ".avif", ".gif"}

# ─── 图片处理（跨进程可序列化调用） ───────────────────────────────


def md5_hash(filepath: str) -> str:
    h = hashlib.md5()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def rgb_to_hsv(r: int, g: int, b: int) -> tuple:
    r, g, b = r / 255.0, g / 255.0, b / 255.0
    mx, mn = max(r, g, b), min(r, g, b)
    d = mx - mn
    if d == 0:
        h = 0
    elif mx == r:
        h = 60 * (((g - b) / d) % 6)
    elif mx == g:
        h = 60 * (((b - r) / d) + 2)
    else:
        h = 60 * (((r - g) / d) + 4)
    s = 0 if mx == 0 else (d / mx) * 100
    v = mx * 100
    return (round(h), round(s), round(v))


def dominant_color(filepath: str) -> tuple:
    if ColorThief is None:
        return (None, None, None, None)
    try:
        ct = ColorThief(filepath)
        r, g, b = ct.get_color(quality=1)
        h, s, v = rgb_to_hsv(r, g, b)
        return (f"#{r:02x}{g:02x}{b:02x}", h, s, v)
    except Exception:
        return (None, None, None, None)


def orientation(w: int, h: int) -> str:
    ratio = w / h if h > 0 else 1
    if ratio > 1.2:
        return "landscape"
    elif ratio < 0.8:
        return "portrait"
    return "square"


def process_one(args: tuple) -> tuple | None:
    """
    处理单张图片（可在 ProcessPoolExecutor 中运行）。
    返回 SQLite 行元组，或 None（跳过）。
    """
    filepath, game, source_type, status, output_dir, thumb_size_str, quality, thumb_quality, existing_md5 = args

    fpath = Path(filepath)
    if fpath.suffix.lower() not in IMAGE_EXTENSIONS:
        return None

    # MD5 去重
    md5 = md5_hash(filepath)
    if md5 in existing_md5:
        return None

    try:
        img = Image.open(filepath)
    except Exception as e:
        print(f"  [错误] 无法打开 {fpath.name}: {e}")
        return None

    w, h = img.size
    orient = orientation(w, h)
    hex_c, hue, sat, val = dominant_color(filepath)

    # 生成文件名：MD5 前 16 位，防枚举
    md5_prefix = md5[:16]
    ext = ".webp"
    slug = f"{game}-{md5_prefix}"
    img_path = f"{game}/{md5_prefix}{ext}"
    thumb_path = f"{game}/thumb_{md5_prefix}{ext}"

    # 保留 ICC Profile 防止颜色偏灰
    icc = img.info.get("icc_profile")

    # 转 RGB（WebP 不支持 CMYK/ RGBA 等）
    if img.mode != "RGB":
        img = img.convert("RGB")

    # BlurHash 生成
    blurhash_str = None
    if blurhash is not None:
        try:
            small = img.copy()
            small.thumbnail((128, 128))
            blurhash_str = blurhash.encode(small, x_components=4, y_components=3)
        except Exception:
            pass

    # pHash 感知哈希（相似度去重用）
    phash_str = None
    if ihash is not None:
        try:
            phash_str = str(ihash.phash(img))
        except Exception:
            pass

    # ── 写入原图 WebP ──
    out_full = Path(output_dir) / img_path
    out_full.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_full, "WEBP", quality=quality, icc_profile=icc)
    fsize = out_full.stat().st_size

    # ── 生成缩略图（智能中心裁剪） ──
    tw, th = map(int, thumb_size_str.split("x"))
    thumb = ImageOps.fit(img, (tw, th), centering=(0.5, 0.5))
    out_thumb = Path(output_dir) / thumb_path
    out_thumb.parent.mkdir(parents=True, exist_ok=True)
    thumb.save(out_thumb, "WEBP", quality=thumb_quality, icc_profile=icc)

    now = datetime.now(timezone.utc).isoformat()
    rk = random.random()

    # ── 从 Pixiv 文件名提取来源链接和画师 ──
    source_url = None
    artist = None
    characters = None
    tags = None

    stem = fpath.stem  # 如 "pixiv_144589079"
    if source_type == "pixiv" and stem.startswith("pixiv_"):
        pixiv_id = stem[6:]  # "144589079"
        source_url = f"https://www.pixiv.net/artworks/{pixiv_id}"

        # 尝试读取 JSON 元数据
        import json as _json
        json_path = fpath.with_suffix(".json")
        if json_path.exists():
            try:
                meta = _json.loads(json_path.read_text(encoding="utf-8"))
                artist = meta.get("artist") or None
                pixiv_tags = meta.get("tags") or []
                if pixiv_tags:
                    tags = _json.dumps(pixiv_tags, ensure_ascii=False)
            except Exception:
                pass

    return (
        slug,
        img_path,
        game,
        characters,
        tags,
        hex_c,
        hue,
        sat,
        val,
        orient,
        w,
        h,
        fsize,
        blurhash_str,  # blurhash
        phash_str,  # phash
        thumb_path,
        source_type,
        source_url,
        artist,
        "official" if source_type == "official" else "unknown",
        0,     # is_ai
        100,   # weight
        rk,
        status,
        None,  # review_comment
        None,  # submitter_contact
        md5,
        now,
    )


# ─── 数据库写入 ───────────────────────────────────────


def load_existing_md5(db_path: str, source_dir: str = None) -> set:
    """加载已存在的 MD5（数据库 + 源目录导入日志）"""
    existing = set()
    if os.path.exists(db_path):
        conn = sqlite3.connect(db_path)
        cur = conn.execute("SELECT md5_hash FROM images WHERE md5_hash IS NOT NULL")
        existing = {row[0] for row in cur.fetchall()}
        conn.close()
    # 第二道防线：源目录的导入日志（独立于数据库，防止记录被删后重复导入）
    if source_dir:
        journal = Path(source_dir) / ".imported_md5"
        if journal.exists():
            existing |= set(journal.read_text().splitlines())
    return existing


def save_source_journal(source_dir: str, md5s: list):
    """追加 MD5 到源目录日志"""
    journal = Path(source_dir) / ".imported_md5"
    with open(journal, "a") as f:
        for m in md5s:
            f.write(f"{m}\n")


def write_to_db(db_path: str, records: list):
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS images (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            slug              TEXT UNIQUE NOT NULL,
            path              TEXT NOT NULL,
            game              TEXT NOT NULL,
            characters        TEXT,
            tags              TEXT,
            dominant_color    TEXT,
            hue               INTEGER,
            saturation        INTEGER,
            value             INTEGER,
            orientation       TEXT NOT NULL,
            width             INTEGER NOT NULL,
            height            INTEGER NOT NULL,
            file_size         INTEGER NOT NULL,
            blurhash          TEXT,
            phash             TEXT,
            thumbnail_path    TEXT,
            source_type       TEXT NOT NULL DEFAULT 'manual',
            source_url        TEXT,
            artist            TEXT,
            authorization     TEXT NOT NULL DEFAULT 'unknown',
            is_ai             INTEGER NOT NULL DEFAULT 0,
            weight            INTEGER NOT NULL DEFAULT 100,
            random_key        REAL NOT NULL,
            status            TEXT NOT NULL DEFAULT 'pending_review',
            review_comment    TEXT,
            submitter_contact TEXT,
            md5_hash          TEXT UNIQUE,
            created_at        TEXT NOT NULL
        )
    """)

    sql = """INSERT OR IGNORE INTO images
        (slug, path, game, characters, tags,
         dominant_color, hue, saturation, value, orientation,
         width, height, file_size, blurhash, phash, thumbnail_path,
         source_type, source_url, artist, authorization,
         is_ai, weight, random_key, status,
         review_comment, submitter_contact, md5_hash, created_at)
        VALUES (?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?,
                ?, ?, ?, ?,
                ?, ?, ?, ?)"""

    conn.executemany(sql, records)
    conn.commit()
    total = conn.execute("SELECT COUNT(*) FROM images").fetchone()[0]
    conn.close()
    print(f"已写入 {len(records)} 条记录 (数据库总计 {total} 张图片)")


# ─── CF Pages _headers 自动生成 ──────────────────────


def write_headers(output_dir: str):
    """生成 CF Pages _headers 文件：CORS + 强缓存"""
    content = """/*
  Access-Control-Allow-Origin: *
  Cache-Control: public, max-age=31536000, immutable
"""
    path = Path(output_dir) / "_headers"
    path.write_text(content, encoding="utf-8")
    print(f"已生成 CF Pages _headers (CORS + 1年强缓存)")


# ─── 主流程 ──────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(description="批量导入图片到 Lumine")
    parser.add_argument("directory", help="图片目录路径")
    parser.add_argument("--game", default="genshin",
                        help="游戏名 (genshin/hsr/zzz/honkai3)")
    parser.add_argument("--source-type", default="manual",
                        choices=["manual", "official", "submission", "pixiv", "bilibili", "hoyowiki", "twitter"])
    parser.add_argument("--status", default="pending_review",
                        choices=["approved", "pending_review", "rejected"])
    parser.add_argument("--db", default=str(Path(__file__).parent.parent
                                            / "backend" / "data" / "lumine.db"),
                        help="SQLite 数据库路径")
    parser.add_argument("--output-dir", default="output/cf-pages",
                        help="WebP + 缩略图输出目录")
    parser.add_argument("--thumb-size", default="400x300",
                        help="缩略图尺寸, WxH")
    parser.add_argument("--quality", type=int, default=85,
                        help="WebP 质量 (1-100)")
    parser.add_argument("--thumb-quality", type=int, default=75,
                        help="缩略图质量 (1-100)")
    parser.add_argument("--dry-run", action="store_true",
                        help="只扫描不写入")
    parser.add_argument("--workers", type=int, default=None,
                        help="并行进程数 (默认 CPU 核心数)")

    args = parser.parse_args()

    if not os.path.isdir(args.directory):
        print(f"错误: 目录不存在 {args.directory}")
        sys.exit(1)

    print(f"扫描目录: {args.directory}")
    print(f"游戏: {args.game} | 来源: {args.source_type} | 状态: {args.status}")
    print(f"输出: {args.output_dir} (WebP q{args.quality}, 缩略图 {args.thumb_size} q{args.thumb_quality})")

    # 收集待处理文件
    files = []
    for fpath in sorted(Path(args.directory).iterdir()):
        if fpath.suffix.lower() in IMAGE_EXTENSIONS:
            files.append(str(fpath))

    print(f"找到 {len(files)} 张图片")

    if not files:
        return

    # 加载已存在的 MD5（数据库 + 源目录日志）
    existing_md5 = load_existing_md5(args.db, args.directory) if not args.dry_run else set()
    print(f"已有 {len(existing_md5)} 个 MD5 (去重用)")

    # 并行处理
    worker_args = [
        (
            f, args.game, args.source_type, args.status,
            args.output_dir, args.thumb_size, args.quality,
            args.thumb_quality, existing_md5,
        )
        for f in files
    ]

    workers = args.workers or os.cpu_count() or 4
    records = []

    if args.dry_run:
        # dry-run: 只统计不处理
        for a in worker_args:
            r = process_one(a)
            if r:
                records.append(r)
    else:
        print(f"使用 {workers} 个进程并行处理...")
        with ProcessPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(process_one, a): a[0] for a in worker_args}
            done = 0
            for future in as_completed(futures):
                done += 1
                r = future.result()
                if r:
                    records.append(r)
                # 进度
                if done % 10 == 0 or done == len(files):
                    pct = done / len(files) * 100
                    print(f"  进度: {done}/{len(files)} ({pct:.0f}%)", end="\r", flush=True)
            print()

    if not records:
        print("没有新图片需要导入。")
        return

    print(f"\n共处理 {len(records)} 张新图片:")
    for r in records[:3]:
        hue_str = f" H={r[7]}°" if r[7] is not None else ""
        print(f"  {r[0]}: {r[1]} ({r[10]}x{r[11]}, {r[9]}, {r[5] or '无色'}{hue_str})")
    if len(records) > 3:
        print(f"  ... 及其他 {len(records) - 3} 张")

    if args.dry_run:
        print("\n[dry-run 模式] 未写入数据库，未生成文件")
        return

    # 写入数据库
    write_to_db(args.db, records)

    # 源目录导入日志（防止数据库记录被删后重复导入）
    new_md5s = [r[26] for r in records if r[26]]
    if new_md5s:
        save_source_journal(args.directory, new_md5s)
        print(f"已记录 {len(new_md5s)} 个 MD5 到源目录日志")

    # 生成 CF Pages _headers
    write_headers(args.output_dir)

    print(f"\n输出目录: {args.output_dir}/")
    print(f"  {args.game}/           ← WebP 原图")
    print(f"  {args.game}/thumb_*    ← 缩略图")
    print(f"  _headers              ← CF Pages 缓存策略")
    print("部署: cd {args.output_dir} && wrangler pages deploy . --project-name lumine-images")


if __name__ == "__main__":
    main()

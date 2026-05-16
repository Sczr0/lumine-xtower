#!/usr/bin/env python3
"""
扫描数据库中黑名单画师的图片，交互式决定是否删除。

用法:
    python scripts/check_blacklist.py

可选参数:
    --db          SQLite 路径, 默认 backend/data/lumine.db
    --image-dir   CDN 图片目录, 默认 output/cf-pages
    --status     筛选特定状态的记录, 默认全部
    --auto-delete 不询问直接删除 (谨慎使用)
    --dry-run     只扫描不操作
"""

import argparse
import sqlite3
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
PROJECT_DIR = SCRIPT_DIR.parent

BLACKLIST_FILE = SCRIPT_DIR / ".artist_blacklist"


def load_blacklist() -> list[str]:
    if not BLACKLIST_FILE.exists():
        print(f"[错误] 黑名单文件不存在: {BLACKLIST_FILE}")
        sys.exit(1)
    artists = [
        line.strip()
        for line in BLACKLIST_FILE.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    return artists


def find_matches(db_path: str, blacklist: list[str], status_filter: str | None) -> list[dict]:
    """查询数据库中匹配黑名单的图片"""
    if not blacklist:
        return []

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    placeholders = ",".join("?" for _ in blacklist)
    where_status = f"AND status = ?" if status_filter else ""

    sql = f"""
        SELECT id, slug, path, thumbnail_path, game, artist,
               source_type, source_url, status, created_at
        FROM images
        WHERE artist IN ({placeholders}) {where_status}
        ORDER BY artist, created_at DESC
    """

    params = blacklist.copy()
    if status_filter:
        params.append(status_filter)

    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def delete_image(db_path: str, image_dir: str, row: dict) -> bool:
    """删除数据库记录和对应的文件"""
    try:
        conn = sqlite3.connect(db_path)
        conn.execute("DELETE FROM images WHERE id = ?", (row["id"],))
        conn.commit()
        conn.close()

        # 删除原图
        img_path = Path(image_dir) / row["path"]
        if img_path.exists():
            img_path.unlink()

        # 删除缩略图
        thumb_path = row["thumbnail_path"]
        if thumb_path:
            thumb_full = Path(image_dir) / thumb_path
            if thumb_full.exists():
                thumb_full.unlink()

        return True
    except Exception as e:
        print(f"    [错误] 删除失败: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="扫描黑名单画师的图片")
    parser.add_argument("--db", default=str(PROJECT_DIR / "backend" / "data" / "lumine.db"),
                        help="SQLite 数据库路径")
    parser.add_argument("--image-dir", default=str(PROJECT_DIR / "output" / "cf-pages"),
                        help="CDN 图片输出目录")
    parser.add_argument("--status", default=None,
                        choices=["pending_review", "approved", "rejected"],
                        help="只筛选特定状态的记录")
    parser.add_argument("--auto-delete", action="store_true",
                        help="不询问直接删除")
    parser.add_argument("--dry-run", action="store_true",
                        help="只扫描不操作")
    args = parser.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        print(f"[错误] 数据库不存在: {db_path}")
        sys.exit(1)

    blacklist = load_blacklist()
    if not blacklist:
        print("黑名单为空，没有需要检查的画师")
        return

    print(f"黑名单画师 ({len(blacklist)} 位): {', '.join(blacklist)}")
    print(f"数据库: {db_path}")
    print(f"图片目录: {args.image_dir}")
    if args.status:
        print(f"筛选状态: {args.status}")
    print()

    matches = find_matches(str(db_path), blacklist, args.status)

    if not matches:
        print("数据库中没有匹配黑名单的图片")
        return

    print(f"找到 {len(matches)} 张匹配的图片:\n")

    # 按画师分组展示
    by_artist: dict[str, list[dict]] = {}
    for m in matches:
        by_artist.setdefault(m["artist"] or "(unknown)", []).append(m)

    for artist, rows in sorted(by_artist.items()):
        print(f"  ── {artist} ({len(rows)} 张) ──")
        for r in rows:
            tag = "[" + r["status"] + "]" if r["status"] else ""
            print(f"    {tag} id={r['id']}  game={r['game']}  "
                  f"slug={r['slug']}  path={r['path']}")
            if r["source_url"]:
                print(f"         来源: {r['source_url']}")
        print()

    if args.dry_run:
        print(f"[DRY RUN] 共 {len(matches)} 张匹配，未执行任何操作")
        return

    if args.auto_delete:
        deleted = 0
        for row in matches:
            if delete_image(str(db_path), args.image_dir, row):
                deleted += 1
        print(f"已删除 {deleted}/{len(matches)} 张图片")
        return

    # 交互式删除
    print("=" * 60)
    print("操作选项:")
    print("  y      — 删除当前图片")
    print("  n      — 跳过当前图片")
    print("  a      — 删除该画师全部图片")
    print("  q      — 退出")
    print("  ?      — 显示详情")
    print("=" * 60)
    print()

    current_artist = None
    artist_auto_delete: set[str] = set()

    for i, row in enumerate(matches, 1):
        artist = row["artist"] or "(unknown)"

        if artist in artist_auto_delete:
            ok = delete_image(str(db_path), args.image_dir, row)
            status = "✓ 已删除" if ok else "✗ 失败"
            print(f"  [{i}/{len(matches)}] [{artist}] {row['slug']} — {status} (批量删除)")
            continue

        if artist != current_artist:
            current_artist = artist
            print(f"\n── {artist} ({sum(1 for r in matches if (r['artist'] or '(unknown)') == artist)} 张) ──")

        print(f"\n  [{i}/{len(matches)}] id={row['id']}  {row['game']}  {row['slug']}")
        if row["source_url"]:
            print(f"      {row['source_url']}")

        while True:
            choice = input("  操作? [y/n/a/q/?] ").strip().lower()
            if choice == "y":
                ok = delete_image(str(db_path), args.image_dir, row)
                print(f"  {'✓ 已删除' if ok else '✗ 删除失败'}")
                break
            elif choice == "n":
                print(f"  - 已跳过")
                break
            elif choice == "a":
                artist_auto_delete.add(artist)
                ok = delete_image(str(db_path), args.image_dir, row)
                print(f"  ✓ 已删除 (后续 {artist} 的图片将自动删除)")
                break
            elif choice == "q":
                print(" 退出")
                remaining = len(matches) - i
                if remaining > 0:
                    print(f"剩余 {remaining} 张未处理")
                return
            elif choice == "?":
                print(f"    游戏: {row['game']}")
                print(f"    画师: {row['artist']}")
                print(f"    状态: {row['status']}")
                print(f"    路径: {row['path']}")
                if row["source_url"]:
                    print(f"    来源: {row['source_url']}")
            else:
                print("    请输入 y/n/a/q/?")

    print(f"\n处理完成, 共处理 {len(matches)} 张")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
从 Pixiv 按标签抓取米哈游相关的同人插画。

依赖:
    pip install pixivpy3 httpx

认证:
    需要 Pixiv 账号的 refresh_token。
    python scripts/pixiv_auth.py login    # 获取 token
    python scripts/crawl_pixiv.py --set-token <TOKEN>  # 保存

用法:
    python scripts/crawl_pixiv.py --game genshin --count 100
    python scripts/crawl_pixiv.py --game genshin --count 100 --use-characters
    python scripts/crawl_pixiv.py --game genshin --count 200 --sort date_desc --use-characters
    python scripts/crawl_pixiv.py --tags "オリジナル,原神" --count 50

输出: tmp/{game}-pixiv/ 目录，可直接用 import_images.py 导入。
"""

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path
from urllib.parse import urlparse, parse_qs as url_parse_qs

try:
    from pixivpy3 import AppPixivAPI
except ImportError:
    print("需要安装 pixivpy3: pip install pixivpy3")
    sys.exit(1)

# ═══════════════════════════════════════════════════════════════
# 配置
# ═══════════════════════════════════════════════════════════════

GAME_TAGS = {
    "genshin": [
        "原神",
        "GenshinImpact",
        "原神10000users入り",
        "Genshin_Impact",
    ],
    "hsr": [
        "崩壊スターレイル",
        "HonkaiStarRail",
        "崩壊スターレイル10000users入り",
        "星穹铁道",
    ],
    "zzz": [
        "ゼンレスゾーンゼロ",
        "ZenlessZoneZero",
        "绝区零",
        "ゼンゼロ10000users入り",
    ],
    "honkai3": [
        "崩壊3rd",
        "HonkaiImpact3rd",
        "崩壊3rd10000users入り",
    ],
}

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp"}
TOKEN_FILE = Path(__file__).parent / ".pixiv_token"
BLACKLIST_FILE = Path(__file__).parent / ".artist_blacklist"

HOYOWIKI_API = "https://sg-wiki-api.hoyolab.com/hoyowiki/wapi/get_entry_page_list"

HOYOWIKI_MENU_IDS = {
    "genshin": "2",
    "hsr": "20",
    "zzz": "47",
    "honkai3": "4",
}


# ═══════════════════════════════════════════════════════════════
# Token 管理
# ═══════════════════════════════════════════════════════════════

def get_token() -> str | None:
    if TOKEN_FILE.exists():
        return TOKEN_FILE.read_text().strip()
    return None


def save_token(token: str):
    TOKEN_FILE.write_text(token)
    try:
        os.chmod(TOKEN_FILE, 0o600)
    except Exception:
        pass
    print(f"Token 已保存到 {TOKEN_FILE}")


# ═══════════════════════════════════════════════════════════════
# 下载
# ═══════════════════════════════════════════════════════════════

def download_illust(api: AppPixivAPI, illust: dict, output_dir: str, seen_ids: set) -> bool:
    """下载一张插画的原图。成功返回 True。"""
    illust_id = illust.get("id")

    # 优先取原图 URL（Pixiv API 直接提供）
    original_url = ""
    meta_single = illust.get("meta_single_page") or {}
    if meta_single.get("original_image_url"):
        original_url = meta_single["original_image_url"]
    else:
        # Fallback: 用 large URL
        urls = illust.get("image_urls", {})
        large_url = urls.get("large", "")
        if large_url:
            original_url = (large_url
                .replace("c/600x1200_90_webp/img-master", "img-original")
                .replace("custom-thumb", "img-original")
                .replace("c/600x1200_90", "img-original")
                .replace("_webp", ""))

    if not original_url:
        return False

    ext = Path(urlparse(original_url).path).suffix
    if ext.lower() not in IMAGE_EXTS:
        ext = ".jpg"

    fname = f"pixiv_{illust_id}{ext}"
    fpath = Path(output_dir) / fname
    if fpath.exists():
        return True

    # 保存元数据 JSON
    try:
        meta = {
            "id": illust_id,
            "title": illust.get("title", ""),
            "artist": illust.get("user", {}).get("name", ""),
            "artist_id": illust.get("user", {}).get("id", ""),
            "tags": [t.get("name", "") for t in illust.get("tags", [])],
            "total_bookmarks": illust.get("total_bookmarks", 0),
            "create_date": illust.get("create_date", ""),
            "width": illust.get("width", 0),
            "height": illust.get("height", 0),
        }
        meta_path = fpath.with_suffix(".json")
        meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass

    # httpx 直链下载（Referer 必须）
    try:
        import httpx
        resp = httpx.get(
            original_url,
            headers={"Referer": "https://www.pixiv.net/"},
            timeout=30,
        )
        resp.raise_for_status()
        fpath.write_bytes(resp.content)
        return True
    except Exception:
        try:
            print(f"\n    下载失败 {illust_id}")
        except Exception:
            pass
        return False


def load_artist_blacklist() -> set:
    if BLACKLIST_FILE.exists():
        return {line.strip() for line in BLACKLIST_FILE.read_text(encoding="utf-8").splitlines()
                if line.strip() and not line.strip().startswith('#')}
    return set()


def add_to_blacklist(name: str):
    blacklist = load_artist_blacklist()
    if name in blacklist:
        print(f"  {name} 已在黑名单中")
        return
    with open(BLACKLIST_FILE, "a", encoding="utf-8") as f:
        f.write(f"{name}\n")
    print(f"  已添加: {name}")


def remove_from_blacklist(name: str):
    blacklist = load_artist_blacklist()
    if name not in blacklist:
        print(f"  {name} 不在黑名单中")
        return
    blacklist.discard(name)
    BLACKLIST_FILE.write_text("\n".join(sorted(blacklist)) + "\n", encoding="utf-8")
    print(f"  已移除: {name}")


def list_blacklist():
    blacklist = load_artist_blacklist()
    if not blacklist:
        print("黑名单为空")
        return
    print(f"黑名单 ({len(blacklist)} 位画师):")
    for name in sorted(blacklist):
        print(f"  - {name}")


# ═══════════════════════════════════════════════════════════════
# 搜索与分页
# ═══════════════════════════════════════════════════════════════

def load_downloaded_ids(output_dir: str) -> set:
    """加载已下载的 Pixiv ID 列表（持久化去重）"""
    id_file = Path(output_dir) / ".downloaded_ids"
    if id_file.exists():
        return set(id_file.read_text().splitlines())
    return set()


def save_downloaded_id(output_dir: str, illust_id):
    """追加一个已下载的 ID"""
    with open(Path(output_dir) / ".downloaded_ids", "a") as f:
        f.write(f"{illust_id}\n")


def fetch_character_names(game_key: str) -> list[str]:
    """从 HoYoWiki 获取角色名称列表"""
    import httpx

    menu_id = HOYOWIKI_MENU_IDS.get(game_key)
    if not menu_id:
        return []

    all_names = []
    page_num = 1
    per_page = 50

    client = httpx.Client(http2=False, timeout=30)

    try:
        while True:
            try:
                resp = client.post(
                    HOYOWIKI_API,
                    json={
                        "filters": [],
                        "menu_id": menu_id,
                        "page_num": page_num,
                        "page_size": per_page,
                    },
                    headers={
                        "Content-Type": "application/json",
                        "x-rpc-wiki_app": "hoyowiki",
                        "x-rpc-language": "zh-cn",
                        "Referer": "https://wiki.hoyolab.com/",
                        "Origin": "https://wiki.hoyolab.com",
                    },
                )
                resp.raise_for_status()
                data = resp.json()
            except Exception as e:
                print(f"  HoYoWiki API 请求失败: {e}")
                break

            if data.get("retcode") != 0:
                break

            entries = data.get("data", {}).get("list", [])
            if not entries:
                break

            for entry in entries:
                name = entry.get("name", "")
                if name:
                    all_names.append(name)

            if len(entries) < per_page:
                break
            page_num += 1
            time.sleep(0.3)
    finally:
        client.close()

    return all_names


def crawl_by_tag(api: AppPixivAPI, tag: str, count: int, output_dir: str, sort: str = "popular_desc", blacklist: set | None = None) -> int:
    """按标签搜索并下载"""
    if blacklist is None:
        blacklist = load_artist_blacklist()

    print(f"\n  搜索标签: \"{tag}\" (目标 {count} 张, {sort})")

    seen_ids = load_downloaded_ids(output_dir)
    skipped = 0
    downloaded = 0
    next_url = None

    while downloaded < count:
        try:
            if next_url:
                qs = api.parse_qs(next_url)
                if not qs:
                    break
                result = api.search_illust(**qs)
            else:
                result = api.search_illust(
                    tag,
                    search_target="partial_match_for_tags",
                    sort=sort,
                )
        except Exception as e:
            print(f"\n    搜索失败: {e}")
            break

        if not result or not result.get("illusts"):
            break

        for illust in result["illusts"]:
            if downloaded >= count:
                break
            illust_id = illust.get("id")
            if illust_id in seen_ids:
                continue
            artist_name = illust.get("user", {}).get("name", "")
            artist_id = illust.get("user", {}).get("id", "")
            if artist_name in blacklist or str(artist_id) in blacklist:
                skipped += 1
                continue
            ok = download_illust(api, illust, output_dir, seen_ids)
            if ok:
                seen_ids.add(illust_id)
                save_downloaded_id(output_dir, illust_id)
                downloaded += 1
                if downloaded % 10 == 0:
                    print(f"    已下载 {downloaded}/{count} ...", end="\r", flush=True)

        next_url = result.get("next_url")
        if not next_url:
            break

        time.sleep(1.5)

    skip_info = f", 跳过 {skipped} 张(黑名单)" if skipped else ""
    print(f"\n    完成: 下载 {downloaded} 张 (标签 \"{tag}\"){skip_info}")
    return downloaded


def crawl_by_characters(api: AppPixivAPI, game_key: str, count: int, sort: str, blacklist: set) -> int:
    """按角色名+游戏名搜索 Pixiv"""
    game_tag = GAME_TAGS[game_key][0]
    print(f"\n  获取 {game_key} 角色列表...")
    characters = fetch_character_names(game_key)
    if not characters:
        print("  未能获取角色列表，回退到标签搜索")
        return _crawl_by_game_tags(api, game_key, count, sort, blacklist)

    print(f"  获取到 {len(characters)} 个角色")

    output_dir = f"tmp/{game_key}-pixiv"
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    per_char = max(count // len(characters), 3)
    print(f"  每角色 {per_char} 张 (共 {len(characters)} 角色, 目标 {count} 张)\n")

    total = 0
    for i, char in enumerate(characters):
        tag = f"{char} {game_tag}"
        n = crawl_by_tag(api, tag, per_char, output_dir, sort, blacklist)
        total += n
        if (i + 1) % 10 == 0:
            print(f"  [{i+1}/{len(characters)}] 已下载 {total} 张")

    return total


def _crawl_by_game_tags(api: AppPixivAPI, game_key: str, count: int, sort: str, blacklist: set) -> int:
    """原有逻辑：按游戏标签搜索"""
    tags = GAME_TAGS.get(game_key, [])
    if not tags:
        print(f"  未配置标签: {game_key}")
        return 0

    output_dir = f"tmp/{game_key}-pixiv"
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    per_tag = max(count // len(tags), 10)
    total = 0
    for tag in tags:
        n = crawl_by_tag(api, tag, per_tag, output_dir, sort, blacklist)
        total += n
    return total


def crawl_game(api: AppPixivAPI, game_key: str, count: int, sort: str = "popular_desc", use_characters: bool = False, blacklist: set | None = None):
    """按游戏抓取"""
    if blacklist is None:
        blacklist = load_artist_blacklist()
    if use_characters:
        return crawl_by_characters(api, game_key, count, sort, blacklist)
    return _crawl_by_game_tags(api, game_key, count, sort, blacklist)


# ═══════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="从 Pixiv 按标签抓取米哈游相关的同人插画"
    )
    parser.add_argument("--set-token", default=None,
                        help="保存 refresh_token (只需执行一次)")
    parser.add_argument("--game", default="genshin",
                        choices=list(GAME_TAGS.keys()),
                        help="目标游戏")
    parser.add_argument("--tags", default=None,
                        help="自定义标签，逗号分隔 (覆盖 --game)")
    parser.add_argument("--count", type=int, default=100,
                        help="下载数量上限")
    parser.add_argument("--sort", default="popular_desc",
                        choices=["popular_desc", "date_desc", "popular_asc", "date_asc"],
                        help="排序方式 (首次用 popular_desc，后续用 date_desc 拿新图)")
    parser.add_argument("--use-characters", action="store_true",
                        help="从 HoYoWiki 获取角色列表，用角色名+游戏名搜索 (更精准)")
    parser.add_argument("--blacklist-add", default=None, metavar="NAME",
                        help="添加画师到黑名单")
    parser.add_argument("--blacklist-remove", default=None, metavar="NAME",
                        help="从黑名单移除画师")
    parser.add_argument("--blacklist-list", action="store_true",
                        help="列出黑名单")
    args = parser.parse_args()

    if args.set_token:
        save_token(args.set_token)
        return

    if args.blacklist_list:
        list_blacklist()
        return

    if args.blacklist_add:
        add_to_blacklist(args.blacklist_add)
        return

    if args.blacklist_remove:
        remove_from_blacklist(args.blacklist_remove)
        return

    token = get_token()
    if not token:
        print("未找到 refresh_token。请先执行:")
        print("  python scripts/pixiv_auth.py login")
        print("  python scripts/crawl_pixiv.py --set-token <TOKEN>")
        sys.exit(1)

    api = AppPixivAPI()
    try:
        api.auth(refresh_token=token)
        print("Pixiv 认证成功")
    except Exception as e:
        print(f"认证失败: {e}")
        sys.exit(1)

    blacklist = load_artist_blacklist()
    if blacklist:
        print(f"已加载黑名单: {len(blacklist)} 位画师")

    if args.tags:
        tags = [t.strip() for t in args.tags.split(",")]
        output_dir = "tmp/custom-pixiv"
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        total = 0
        per_tag = max(args.count // len(tags), 10)
        for tag in tags:
            n = crawl_by_tag(api, tag, per_tag, output_dir, args.sort, blacklist)
            total += n
        game_label = "custom"
    else:
        game_label = args.game
        total = crawl_game(api, args.game, args.count, args.sort,
                           use_characters=args.use_characters, blacklist=blacklist)

    print(f"\n{'='*60}")
    print(f"总计下载 {total} 张新图片")
    output_dir = f"tmp/{game_label}-pixiv"
    if Path(output_dir).exists():
        img_count = len([f for f in Path(output_dir).iterdir() if f.suffix in IMAGE_EXTS])
        print(f"  {output_dir}/  ({img_count} 张图片)")
    print(f"\n下一步导入:")
    print(f"  python scripts/import_images.py {output_dir} \\")
    print(f"      --source-type pixiv --status pending_review")


if __name__ == "__main__":
    main()

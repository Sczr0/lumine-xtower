#!/usr/bin/env python3
"""
从米哈游官方渠道抓取壁纸和美术图。

来源:
  1. Bilibili 官方账号动态 (国服 KV、PV 截图、活动壁纸)
  2. HoYoWiki API (角色立绘、设定图)

用法:
    python scripts/crawl_website.py --game genshin --source bilibili
    python scripts/crawl_website.py --game genshin --source hoyowiki
    python scripts/crawl_website.py --game all --source all

输出: tmp/{game}-website/ 目录，可直接用 import_images.py 导入。
"""

import argparse
import hashlib
import json
import os
import re
import sys
import time
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlencode, urlparse

import httpx

# ═══════════════════════════════════════════════════════════════
# 游戏配置
# ═══════════════════════════════════════════════════════════════

GAME_CONFIG = {
    "genshin": {
        "name": "原神",
        "bilibili_uid": "401742377",
    },
    "hsr": {
        "name": "崩坏：星穹铁道",
        "bilibili_uid": "1340190821",
    },
    "zzz": {
        "name": "绝区零",
        "bilibili_uid": "1636375920",
    },
    "honkai3": {
        "name": "崩坏3",
        "bilibili_uid": "27534330",
    },
}

BILIBILI_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

BILIBILI_IMG_DOMAINS = {
    "i0.hdslb.com", "i1.hdslb.com", "i2.hdslb.com",
    "archive.biliimg.com", "pic.bstarstatic.com",
}

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp"}


# ═══════════════════════════════════════════════════════════════
# Bilibili WBI 签名
# ═══════════════════════════════════════════════════════════════

_WBI_KEYS: tuple[str, str] | None = None  # (img_key, sub_key) cache


def _fetch_wbi_keys(client: httpx.Client) -> tuple[str, str]:
    """从 Bilibili nav 接口获取 WBI 密钥对"""
    global _WBI_KEYS
    if _WBI_KEYS is not None:
        return _WBI_KEYS

    resp = client.get(
        "https://api.bilibili.com/x/web-interface/nav",
        headers={"User-Agent": BILIBILI_USER_AGENT},
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()
    wbi = data.get("data", {}).get("wbi_img", {})
    # WBI 密钥从 URL 中提取（文件名去后缀即密钥）
    img_key = Path(urlparse(wbi.get("img_key", "") or wbi.get("img_url", "")).path).stem
    sub_key = Path(urlparse(wbi.get("sub_key", "") or wbi.get("sub_url", "")).path).stem
    if not img_key or not sub_key:
        raise RuntimeError(f"无法获取 WBI 密钥: {wbi}")

    _WBI_KEYS = (img_key, sub_key)
    return _WBI_KEYS


def _wbi_sign(params: dict, img_key: str, sub_key: str) -> dict:
    """对参数字典做 WBI 签名，添加 w_rid 和 wts"""
    mix_key = (img_key[:16] + sub_key[:16])
    params["wts"] = int(time.time())
    # 按 key 排序，拼接成 query string，追加密钥，MD5
    sorted_params = sorted(params.items(), key=lambda x: x[0])
    raw = urlencode(sorted_params) + mix_key
    w_rid = hashlib.md5(raw.encode()).hexdigest()
    params["w_rid"] = w_rid
    return params


_bili_cookie: str | None = None


def set_bilibili_cookie(cookie: str | None):
    global _bili_cookie
    _bili_cookie = cookie


def bilibili_get(client: httpx.Client, url: str, params: dict, referer: str) -> httpx.Response:
    """带 WBI 签名和登录态的 Bilibili GET 请求"""
    img_key, sub_key = _fetch_wbi_keys(client)
    signed = _wbi_sign(params.copy(), img_key, sub_key)
    headers = {
        "User-Agent": BILIBILI_USER_AGENT,
        "Referer": referer,
    }
    if _bili_cookie:
        headers["Cookie"] = f"SESSDATA={_bili_cookie}"
    resp = client.get(url, params=signed, headers=headers, timeout=30)
    return resp


# ═══════════════════════════════════════════════════════════════
# Bilibili 动态爬取
# ═══════════════════════════════════════════════════════════════

BILIBILI_SPACE_API = "https://api.bilibili.com/x/polymer/web-dynamic/v1/feed/space"


def parse_bilibili_imgs(item: dict) -> list[dict]:
    """从一条 Bilibili 动态中提取图片 URL"""
    modules = item.get("modules", {})
    pics = []

    major = modules.get("module_dynamic", {}).get("major", {})
    draw_items = major.get("draw", {}).get("items", [])
    for di in draw_items:
        src = di.get("src", "")
        if src:
            pics.append({"url": src, "desc": ""})

    # 动态文本中嵌入的图片
    desc = modules.get("module_dynamic", {}).get("desc", {})
    text = desc.get("text", "")
    if text:
        urls_in_text = re.findall(
            r'https?://[^\s"\'<>]+\.(?:png|jpg|jpeg|webp)(?:\?[^\s"\'<>]*)?',
            text,
        )
        for u in urls_in_text:
            parsed = urlparse(u)
            if parsed.netloc in BILIBILI_IMG_DOMAINS:
                pics.append({"url": u, "desc": ""})

    return pics


def crawl_bilibili(uid: str, game_key: str, max_pages: int, client: httpx.Client) -> int:
    """爬取 Bilibili 官方账号动态中的图片"""
    print(f"\n  [Bilibili] 爬取 uid={uid} 的动态...")

    output_dir = f"tmp/{game_key}-website"
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    downloaded = 0
    seen_urls = set()
    offset = ""

    for page in range(max_pages):
        params = {
            "host_mid": uid,
            "offset": offset,
            "features": "itemOpusStyle,opusBigCover,decorationCard,onlyfansVote",
        }
        referer = f"https://space.bilibili.com/{uid}/dynamic"

        try:
            resp = bilibili_get(client, BILIBILI_SPACE_API, params, referer)
            data = resp.json()
        except Exception as e:
            print(f"    第 {page + 1} 页请求失败: {e}")
            break

        code = data.get("code")
        if code != 0:
            msg = data.get("message", "")
            print(f"    API 返回 code={code}: {msg}")
            if code == -352:
                print("    → 风控拦截，Bilibili 要求浏览器验证。请手动打开")
                print(f"      https://space.bilibili.com/{uid}/dynamic")
                print(f"      完成验证后重试。")
            break

        result = data.get("data", {})
        items = result.get("items", [])
        offset = result.get("offset", "")
        has_more = result.get("has_more", False)

        if not items:
            break

        for item in items:
            pics = parse_bilibili_imgs(item)
            for pic in pics:
                url = pic["url"]
                if url in seen_urls:
                    continue
                seen_urls.add(url)

                url_hash = hashlib.md5(url.encode()).hexdigest()[:16]
                ext = Path(urlparse(url).path).suffix or ".jpg"
                fname = f"bili_{url_hash}{ext}"
                fpath = Path(output_dir) / fname

                if fpath.exists():
                    continue

                try:
                    img_resp = client.get(
                        url,
                        headers={"User-Agent": BILIBILI_USER_AGENT, "Referer": referer},
                        timeout=30,
                    )
                    img_resp.raise_for_status()
                    fpath.write_bytes(img_resp.content)
                    downloaded += 1
                except Exception as e:
                    print(f"      下载失败 {fname}: {e}")

        pct = min(page + 1, max_pages) / max_pages * 100
        print(f"    第 {page + 1}/{max_pages} 页 ({pct:.0f}%)  已下载 {downloaded} 张",
              end="\r", flush=True)

        if not has_more:
            break

        time.sleep(1.5)

    print(f"\n    [Bilibili] 完成: 下载 {downloaded} 张新图")
    return downloaded


# ═══════════════════════════════════════════════════════════════
# HoYoWiki 角色图爬取
# ═══════════════════════════════════════════════════════════════

HOYOWIKI_API = "https://sg-wiki-api.hoyolab.com/hoyowiki/wapi/get_entry_page_list"

HOYOWIKI_MENU_IDS = {
    "genshin": "2",
    "hsr": "20",
    "zzz": "47",
    "honkai3": "4",
}


def crawl_hoyowiki(game_key: str, client: httpx.Client) -> int:
    """从 HoYoWiki 获取角色立绘和设定图"""
    print(f"\n  [HoYoWiki] 爬取 {GAME_CONFIG[game_key]['name']} 角色图...")

    output_dir = f"tmp/{game_key}-website"
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    menu_id = HOYOWIKI_MENU_IDS.get(game_key)
    if not menu_id:
        print(f"    HoYoWiki 不支持 {game_key}")
        return 0

    downloaded = 0
    seen_urls = set()
    api_client = httpx.Client(http2=False, timeout=30)

    # 分页拉取（page_size 最大 50）
    all_entries = []
    page_num = 1
    per_page = 50

    while True:
        try:
            resp = api_client.post(
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
            print(f"    HoYoWiki API 请求失败: {e}")
            break

        if data.get("retcode") != 0:
            print(f"    HoYoWiki API 错误: retcode={data.get('retcode')} {data.get('message', '')}")
            break

        entries = data.get("data", {}).get("list", [])
        if not entries:
            break

        all_entries.extend(entries)
        if len(entries) < per_page:
            break
        page_num += 1
        time.sleep(0.5)

    api_client.close()
    print(f"    获取到 {len(all_entries)} 个条目")

    for entry in all_entries:
        images = extract_images_recursive(entry)
        for img_url in images:
            if img_url in seen_urls:
                continue
            seen_urls.add(img_url)

            url_hash = hashlib.md5(img_url.encode()).hexdigest()[:16]
            ext = Path(urlparse(img_url).path).suffix or ".png"
            if ext.lower() not in IMAGE_EXTS:
                continue
            fname = f"wiki_{url_hash}{ext}"
            fpath = Path(output_dir) / fname

            if fpath.exists():
                continue

            try:
                img_resp = client.get(img_url, timeout=30)
                img_resp.raise_for_status()
                fpath.write_bytes(img_resp.content)
                downloaded += 1
                if downloaded % 10 == 0:
                    print(f"    已下载 {downloaded} 张...", end="\r", flush=True)
            except Exception as e:
                print(f"      下载失败 {fname}: {e}")

            time.sleep(0.3)

    print(f"\n    [HoYoWiki] 完成: 下载 {downloaded} 张新图")
    return downloaded


def extract_images_recursive(obj, depth=0) -> set[str]:
    """递归从 JSON 对象中提取所有图片 URL"""
    if depth > 15:
        return set()

    urls = set()
    if isinstance(obj, dict):
        for key in ("url", "icon", "avatar", "cover", "banner",
                     "image", "img", "background", "pic", "src", "full"):
            if key in obj and isinstance(obj[key], str):
                v = obj[key]
                if any(v.lower().endswith(ext) for ext in IMAGE_EXTS):
                    urls.add(v.split("?")[0])
        for v in obj.values():
            urls.update(extract_images_recursive(v, depth + 1))
        if "content" in obj and isinstance(obj["content"], str):
            found = re.findall(
                r'https?://[^\s"\'<>]+\.(?:png|jpg|jpeg|webp)',
                obj["content"],
            )
            urls.update(u.split("?")[0] for u in found)
    elif isinstance(obj, list):
        for item in obj:
            urls.update(extract_images_recursive(item, depth + 1))
    return urls


# ═══════════════════════════════════════════════════════════════
# 主流程
# ═══════════════════════════════════════════════════════════════


def main():
    parser = argparse.ArgumentParser(
        description="从米哈游官方渠道抓取壁纸和美术图"
    )
    parser.add_argument("--game", default="all",
                        choices=["all"] + list(GAME_CONFIG.keys()),
                        help="目标游戏，默认 all")
    parser.add_argument("--source", default="all",
                        choices=["all", "bilibili", "hoyowiki"],
                        help="数据来源，默认 all")
    parser.add_argument("--pages", type=int, default=3,
                        help="Bilibili 爬取页数 (每页约 10 条动态)")
    parser.add_argument("--cookie", default=None,
                        help="Bilibili SESSDATA cookie (浏览器登录后从 F12 复制)")
    args = parser.parse_args()

    games = list(GAME_CONFIG.keys()) if args.game == "all" else [args.game]
    sources = ["bilibili", "hoyowiki"] if args.source == "all" else [args.source]

    if "bilibili" in sources:
        set_bilibili_cookie(args.cookie)

    print(f"=== 官网图片抓取 ===")
    print(f"游戏: {[GAME_CONFIG[g]['name'] for g in games]}")
    print(f"来源: {sources}")
    print()

    total = 0

    with httpx.Client(http2=True, timeout=60) as client:
        for game_key in games:
            print(f"\n{'='*60}")
            print(f"  {GAME_CONFIG[game_key]['name']}")
            print(f"{'='*60}")

            if "bilibili" in sources:
                uid = GAME_CONFIG[game_key]["bilibili_uid"]
                n = crawl_bilibili(uid, game_key, args.pages, client)
                total += n

            if "hoyowiki" in sources:
                n = crawl_hoyowiki(game_key, client)
                total += n

    print(f"\n{'='*60}")
    print(f"总计下载 {total} 张新图片")
    for game_key in games:
        d = f"tmp/{game_key}-website"
        if Path(d).exists():
            count = len(list(Path(d).iterdir()))
            print(f"  {d}/  ({count} 个文件)")
    print(f"\n下一步导入:")
    for game_key in games:
        d = f"tmp/{game_key}-website"
        if Path(d).exists():
            print(f"  python scripts/import_images.py {d} --game {game_key} \\")
            print(f"      --source-type bilibili --status pending_review")


if __name__ == "__main__":
    main()

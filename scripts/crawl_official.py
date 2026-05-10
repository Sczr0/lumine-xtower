#!/usr/bin/env python3
"""
爬取米哈游官方新闻/公告中的图片。

用法:
    python scripts/crawl_official.py --game genshin --pages 5

来源: HoYoVerse 公开 API
输出: tmp/{game}-crawl/ 目录，可直接用 import_images.py 导入。
"""

import argparse
import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

import httpx

# 各游戏的 HoYoVerse Blackboard API
GAME_CONFIG = {
    "genshin": {
        "app_id": "1",
        "language": "en-us",
    },
    "hsr": {
        "app_id": "3",
        "language": "en-us",
    },
    "zzz": {
        "app_id": "17",
        "language": "en-us",
    },
    "honkai3": {
        "app_id": "2",
        "language": "en-us",
    },
}

API_URL = "https://sg-public-api.hoyoverse.com/common/blackboard/content/page/list"

# 图片 CDN 域名白名单
ALLOWED_DOMAINS = {
    "upload-os-bbs.hoyolab.com",
    "upload-os-bbs.mihoyo.com",
    "webstatic.hoyoverse.com",
    "webstatic.mihoyo.com",
    "act-webstatic.hoyoverse.com",
    "act-webstatic.mihoyo.com",
    "sdk-static.mihoyo.com",
    "img-os-bbs.hoyolab.com",
}


def is_image_url(url: str) -> bool:
    """判断是否为允许来源的图片"""
    try:
        domain = urlparse(url).netloc
        return domain in ALLOWED_DOMAINS and any(
            url.lower().endswith(ext) for ext in (".png", ".jpg", ".jpeg", ".webp")
        )
    except Exception:
        return False


def extract_images(obj, depth=0) -> set[str]:
    """递归从 JSON 对象中提取图片 URL"""
    if depth > 20:
        return set()

    urls = set()
    if isinstance(obj, dict):
        # 常见图片字段名
        for key in ("url", "image", "img", "icon", "avatar", "cover", "banner",
                    "background", "logo", "pic", "src"):
            if key in obj and isinstance(obj[key], str) and is_image_url(obj[key]):
                urls.add(obj[key])

        for v in obj.values():
            urls.update(extract_images(v, depth + 1))

        # 富文本内容中提取
        if "content" in obj and isinstance(obj["content"], str):
            urls.update(
                m.group(0) for m in re.finditer(
                    r'https?://[^\s"\'<>]+\.(?:png|jpg|jpeg|webp)(?:\?[^\s"\'<>]*)?',
                    obj["content"]
                )
            )

    elif isinstance(obj, list):
        for item in obj:
            urls.update(extract_images(item, depth + 1))

    return {u for u in urls if is_image_url(u)}


def fetch_page(app_id: str, language: str, page_no: int) -> list[dict] | None:
    """获取一页新闻列表"""
    params = {
        "app_id": app_id,
        "page_size": "20",
        "page_no": str(page_no),
        "language": language,
    }
    try:
        resp = httpx.get(API_URL, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        if data.get("retcode") == 0:
            # 从 data 中提取文章列表，实际路径取决于 API 返回结构
            content = data.get("data", {})
            # 尝试不同路径
            if "list" in content:
                return content["list"]
            elif "items" in content:
                return content["items"]
            elif isinstance(content, list):
                return content
            else:
                # 看看里面到底是什么结构
                return [content]
        else:
            print(f"  API 返回错误: {data.get('retcode')} {data.get('message', '')}")
            return None
    except Exception as e:
        print(f"  请求失败: {e}")
        return None


def crawl_images(app_id: str, language: str, max_pages: int, output_dir: str):
    """爬取文章列表，提取图片，保存到本地"""
    total_images = set()
    downloaded = 0

    with httpx.Client() as client:
        for page_no in range(1, max_pages + 1):
            print(f"  第 {page_no} 页...")
            articles = fetch_page(app_id, language, page_no)
            if not articles:
                print(f"    无更多数据，停止")
                break

            for article in articles:
                images = extract_images(article)
                if not images:
                    continue

                title = article.get("title", "") or article.get("subject", "")
                print(f"    {title[:40] if title else '(无标题)'}: {len(images)} 张图")

                for url in images:
                    if url in total_images:
                        continue
                    total_images.add(url)
                    fname = download_image(url, output_dir, client)
                    if fname:
                        downloaded += 1

            time.sleep(0.5)  # 礼貌间隔

    return total_images, downloaded


def download_image(url: str, output_dir: str, client: httpx.Client) -> str | None:
    """下载单张图片"""
    url_hash = hashlib.md5(url.encode()).hexdigest()[:16]
    ext = Path(urlparse(url).path).suffix or ".jpg"
    fname = f"{url_hash}{ext}"
    fpath = Path(output_dir) / fname

    if fpath.exists():
        return None

    try:
        resp = client.get(url, timeout=30)
        resp.raise_for_status()
        fpath.write_bytes(resp.content)
        return fname
    except Exception as e:
        print(f"      [下载失败] {fname}: {e}")
        return None


def main():
    parser = argparse.ArgumentParser(description="爬取米哈游官方新闻图片")
    parser.add_argument("--game", default="genshin",
                        choices=list(GAME_CONFIG.keys()))
    parser.add_argument("--pages", type=int, default=5,
                        help="爬取页数 (每页 20 篇文章)")
    parser.add_argument("--output", default=None,
                        help="输出目录")
    args = parser.parse_args()

    cfg = GAME_CONFIG[args.game]
    output_dir = args.output or f"tmp/{args.game}-crawl"
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    print(f"=== 爬取 {args.game} 官方新闻 ===")
    print(f"输出: {output_dir}/ | 最多 {args.pages} 页")

    images, downloaded = crawl_images(
        cfg["app_id"], cfg["language"], args.pages, output_dir
    )

    print(f"\n完成: 发现 {len(images)} 张图片，下载 {downloaded} 张新图")
    print(f"输出目录: {output_dir}/")
    print(f"\n下一步导入:")
    print(f"  python scripts/import_images.py {output_dir} --game {args.game} \\")
    print(f"      --source-type official --status approved")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""准备 VPS 部署包 — 跨平台版本
用法: python deploy/prepare.py
输出: deploy/vps/ 目录，可直接 scp/rsync 到 VPS
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
DST = ROOT / "deploy" / "vps"

def step(msg):
    print(f"\033[36m{msg}\033[0m")

def run(cmd, cwd=None):
    print(f"  $ {cmd}")
    subprocess.run(cmd, shell=True, check=True, cwd=cwd or ROOT)

def main():
    print("=== Lumine VPS 部署包准备 ===\n")

    # ── 1. 前端构建 ──
    frontend_dist = ROOT / "frontend" / "dist"
    if not (frontend_dist / "index.html").exists():
        step("[1/5] 构建前端...")
        run("npm run build", cwd=ROOT / "frontend")
    else:
        step("[1/5] 前端 dist/ 已存在，跳过构建")

    # ── 2. 打标台构建 ──
    tagging_dist = ROOT / "frontend" / "tagging" / "dist"
    if not (tagging_dist / "index.html").exists():
        step("[2/5] 构建打标台...")
        run("npm run build", cwd=ROOT / "frontend" / "tagging")
    else:
        step("[2/5] 打标台 dist/ 已存在，跳过构建")

    # ── 3. 后端构建（可选，可能需要在 Linux 上交叉编译）──
    backend_bin = ROOT / "backend" / "target" / "release" / "lumine-api"
    if not backend_bin.exists():
        step("[3/5] 后端二进制不存在，跳过（需在 Linux 下编译或交叉编译）")
        backend_available = False
    else:
        step("[3/5] 后端二进制已存在")
        backend_available = True

    # ── 4. 收集文件 ──
    step("[4/5] 收集部署文件...")

    # 清理目标目录
    if DST.exists():
        shutil.rmtree(DST)
    DST.mkdir(parents=True)

    # 创建目录结构
    dirs = [
        DST / "etc" / "caddy" / "sites",
        DST / "etc" / "systemd" / "system",
        DST / "opt" / "lumine" / "data",
        DST / "opt" / "lumine" / "static" / "tagging",
    ]
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)

    # Caddy 站点片段
    caddyfile = ROOT / "deploy" / "Caddyfile"
    if caddyfile.exists():
        shutil.copy2(caddyfile, DST / "etc" / "caddy" / "sites" / "lumine")
        print(f"  + deploy/vps/etc/caddy/sites/lumine")

    # 前端静态文件
    if (frontend_dist).exists():
        for item in frontend_dist.iterdir():
            dest = DST / "opt" / "lumine" / "static" / item.name
            if item.is_dir():
                if dest.exists():
                    shutil.rmtree(dest)
                shutil.copytree(item, dest)
            else:
                shutil.copy2(item, dest)
        print(f"  + deploy/vps/opt/lumine/static/  (前端)")

    # 打标台
    if tagging_dist.exists():
        tagging_dst = DST / "opt" / "lumine" / "static" / "tagging"
        for item in tagging_dist.iterdir():
            dest = tagging_dst / item.name
            if item.is_dir():
                if dest.exists():
                    shutil.rmtree(dest)
                shutil.copytree(item, dest)
            else:
                shutil.copy2(item, dest)
        print(f"  + deploy/vps/opt/lumine/static/tagging/  (打标台)")

    # 后端二进制
    if backend_available:
        shutil.copy2(backend_bin, DST / "opt" / "lumine" / "lumine-api")
        print(f"  + deploy/vps/opt/lumine/lumine-api")

    # 数据库
    db = ROOT / "backend" / "data" / "lumine.db"
    if db.exists():
        shutil.copy2(db, DST / "opt" / "lumine" / "data" / "lumine.db")
        print(f"  + deploy/vps/opt/lumine/data/lumine.db")

    # .env
    env_file = ROOT / "backend" / ".env"
    if env_file.exists():
        shutil.copy2(env_file, DST / "opt" / "lumine" / ".env")
        print(f"  + deploy/vps/opt/lumine/.env")

    # ── 5. 生成 systemd 服务文件 ──
    step("[5/5] 生成 systemd 服务文件...")
    service_content = """[Unit]
Description=Lumine API Server
After=network.target

[Service]
Type=simple
User=lumine
WorkingDirectory=/opt/lumine
ExecStart=/opt/lumine/lumine-api
Restart=always
RestartSec=5
Environment=RUST_LOG=info

[Install]
WantedBy=multi-user.target
"""
    (DST / "etc" / "systemd" / "system" / "lumine.service").write_text(service_content)
    print(f"  + deploy/vps/etc/systemd/system/lumine.service")

    # ── gitignore ──
    (DST / ".gitignore").write_text("# 全部忽略，防止误提交构建产物和敏感文件\n*\n!.gitignore\n")

    # ── 完成 ──
    print(f"\n=== 部署包已生成: {DST} ===\n")
    print("上传命令:\n")
    print("  # 1. Caddyfile")
    print("  scp deploy/vps/caddy/Caddyfile                        user@<VPS>:/etc/caddy/")
    print("")
    print("  # 2. 应用文件（后端+静态+数据库+.env）")
    print("  scp -r deploy/vps/opt/lumine/*                         user@<VPS>:/opt/lumine/")
    print("")
    print("  # 3. systemd 服务")
    print("  scp deploy/vps/systemd/lumine.service                  user@<VPS>:/etc/systemd/system/")
    print("")
    print("  # 4. VPS 重启服务")
    print("  ssh user@<VPS> 'sudo chown -R lumine:lumine /opt/lumine && \\")
    print("                   sudo systemctl daemon-reload && \\")
    print("                   sudo systemctl restart lumine caddy'")

if __name__ == "__main__":
    main()

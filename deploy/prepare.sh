#!/usr/bin/env bash
# 准备 VPS 部署包
# 用法: bash deploy/prepare.sh
# 输出: deploy/vps/ 目录，可直接 scp 到 VPS

set -euo pipefail
cd "$(dirname "$0")/.."

echo "=== Lumine VPS 部署包准备 ==="

# ── 1. 前端构建 ──
if [ ! -d "frontend/dist" ]; then
    echo "[1/5] 构建前端..."
    cd frontend && npm run build && cd ..
else
    echo "[1/5] 前端 dist/ 已存在，跳过构建"
fi

# ── 2. 打标台构建 ──
if [ ! -d "frontend/tagging/dist" ]; then
    echo "[2/5] 构建打标台..."
    cd frontend/tagging && npm run build && cd ../..
else
    echo "[2/5] 打标台 dist/ 已存在，跳过构建"
fi

# ── 3. 后端构建 ──
if [ ! -f "backend/target/release/lumine-api" ]; then
    echo "[3/5] 构建后端..."
    cd backend && cargo build --release && cd ..
else
    echo "[3/5] 后端二进制已存在，跳过构建"
fi

# ── 4. 收集文件 ──
echo "[4/5] 收集部署文件..."

DST="deploy/vps"

# Caddyfile
cp -v deploy/Caddyfile "$DST/caddy/"

# 前端静态文件
rsync -av --delete frontend/dist/ "$DST/opt/lumine/static/"

# 打标台
if [ -d "frontend/tagging/dist" ]; then
    rsync -av --delete frontend/tagging/dist/ "$DST/opt/lumine/static/tagging/"
fi

# 后端二进制
cp -v backend/target/release/lumine-api "$DST/opt/lumine/"

# 数据库
cp -v backend/data/lumine.db "$DST/opt/lumine/data/"

# .env
cp -v backend/.env "$DST/opt/lumine/"

# ── 5. 生成 systemd 服务文件 ──
echo "[5/5] 生成 systemd 服务文件..."
cat > "$DST/systemd/lumine.service" << 'SYSTEMD'
[Unit]
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
SYSTEMD

# ── 完成 ──
echo ""
echo "=== 部署包已生成: $DST/ ==="
echo ""
echo "目录结构:"
find "$DST" -type f | sed "s|$DST|deploy/vps|" | sort
echo ""
echo "上传命令:"
echo "  # 1. Caddyfile"
echo "  scp deploy/vps/caddy/Caddyfile                        user@<VPS>:/etc/caddy/"
echo ""
echo "  # 2. 应用文件"
echo "  scp -r deploy/vps/opt/lumine/*                         user@<VPS>:/opt/lumine/"
echo ""
echo "  # 3. systemd 服务"
echo "  scp deploy/vps/systemd/lumine.service                  user@<VPS>:/etc/systemd/system/"
echo ""
echo "  # 4. 在 VPS 上执行"
echo "  ssh user@<VPS> 'sudo chown -R lumine:lumine /opt/lumine && sudo systemctl daemon-reload && sudo systemctl restart lumine caddy'"

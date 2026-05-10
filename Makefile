.PHONY: all frontend backend clean run

all: frontend backend

# 前端构建
frontend:
	cd frontend && npm install && npm run build

# 后端构建
backend:
	cd backend && cargo build --release

# 前端开发
frontend-dev:
	cd frontend && npm run dev

# 生产启动（前端构建产物由 Rust 二进制 serve）
run:
	cd backend && cargo run --release

# 清理
clean:
	rm -rf frontend/dist
	cd backend && cargo clean

# 快速开发（只编译后端，前端需提前 build 好）
dev:
	cd backend && cargo run

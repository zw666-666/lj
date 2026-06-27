#!/bin/bash
# ==========================================
# 律镜 LawMirror — 前端启动脚本
# 使用方法：bash start_frontend.sh
# ==========================================
set -e

# 进入 frontend 目录
cd "$(dirname "$0")/frontend"

# 检查 Node.js 是否可用
if ! command -v node &>/dev/null; then
    echo "❌ 未找到 Node.js，请先安装 Node.js 18+"
    exit 1
fi

echo ">>> Node.js: $(node --version)"
echo ">>> npm: $(npm --version)"

# 安装依赖（如 node_modules 不存在则安装）
if [ ! -d "node_modules" ]; then
    echo ">>> 安装 npm 依赖..."
    npm install
fi

# 启动 Vite 开发服务器
echo ">>> 启动 Vue3 前端 (http://127.0.0.1:3000)..."
echo "    后端 API 代理: /api → http://127.0.0.1:8000"
echo ""
npm run dev

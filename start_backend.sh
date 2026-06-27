#!/bin/bash
# ==========================================
# 律镜 LawMirror — 后端启动脚本
# 使用方法：bash start_backend.sh
# ==========================================
set -e

# 进入 backend 目录
cd "$(dirname "$0")/backend"

# 检查 Python 是否可用
if ! command -v python &>/dev/null; then
    echo "❌ 未找到 Python，请先安装 Python 3.10+"
    exit 1
fi

echo ">>> Python: $(python --version)"

# 创建虚拟环境（如不存在）
if [ ! -d "venv" ]; then
    echo ">>> 创建 Python 虚拟环境..."
    python -m venv venv
fi

# 激活虚拟环境
if [ -f "venv/Scripts/activate" ]; then
    source venv/Scripts/activate
elif [ -f "venv/bin/activate" ]; then
    source venv/bin/activate
else
    echo "❌ 虚拟环境未找到，请手动创建"
    exit 1
fi

# 安装依赖
echo ">>> 安装 Python 依赖..."
pip install -q -r requirements.txt

# 清理 Python 字节码缓存，确保新代码生效
echo ">>> 清理 __pycache__ ..."
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true

# 通过 run.py 启动（run.py 内置了端口冲突自动处理）
echo ">>> 启动 FastAPI 后端 (http://127.0.0.1:8000)..."
echo ">>> 启动 FastAPI 后端 (http://127.0.0.1:8000)..."
echo "    API 文档: http://127.0.0.1:8000/docs"
echo "    健康检查: http://127.0.0.1:8000/api/health"
echo ""
python run.py

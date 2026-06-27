"""律镜后端启动入口 —— 自动处理 vendor 路径和端口冲突"""
import sys
import os
import subprocess

# 获取 backend 目录
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 将 backend 目录加入 Python 路径（保证 app 包可导入）
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

# 将 vendor 目录加入 Python 路径（追加到末尾，让 pip 安装的包优先）
vendor_path = os.path.join(BASE_DIR, "vendor")
if os.path.isdir(vendor_path) and vendor_path not in sys.path:
    sys.path.append(vendor_path)

# 设置 PYTHONPATH 让 uvicorn reload 子进程也能正确导入
existing = os.environ.get("PYTHONPATH", "")
paths = [BASE_DIR, vendor_path]
if existing:
    paths.append(existing)
os.environ["PYTHONPATH"] = os.pathsep.join(paths)


def free_port_8000():
    """检查并释放 8000 端口（Windows）"""
    try:
        result = subprocess.run(
            ['netstat', '-ano'], capture_output=True, text=True, timeout=5
        )
        for line in result.stdout.split('\n'):
            if ':8000' in line and 'LISTENING' in line:
                parts = line.split()
                pid = parts[-1]
                print(f'[run.py] 端口 8000 被占用 (PID {pid})，正在释放...')
                subprocess.run(
                    f'taskkill //F //PID {pid}',
                    capture_output=True, shell=True,
                )
    except Exception as e:
        print(f'[run.py] 端口检查失败: {e}')


if __name__ == "__main__":
    import time
    free_port_8000()
    time.sleep(1)
    import uvicorn
    from app.main import app
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=False)

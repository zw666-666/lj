@echo off
chcp 65001 >nul
title 律镜 - FastAPI 后端

cd /d "%~dp0backend"

echo.
echo ========================================
echo   律镜 LawMirror - 后端启动中...
echo   API 文档: http://192.168.10.27:8000/docs
echo   健康检查: http://192.168.10.27:8000/api/health
echo ========================================
echo.

uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

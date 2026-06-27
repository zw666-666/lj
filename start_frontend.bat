@echo off
chcp 65001 >nul
title 律镜 - Vue3 前端

cd /d "%~dp0frontend"

echo.
echo ========================================
echo   律镜 LawMirror - 前端启动中...
echo   访问地址: http://192.168.10.27:3000
echo ========================================
echo.

npm run dev -- --host 0.0.0.0

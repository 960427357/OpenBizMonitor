@echo off
chcp 65001 >nul
echo.
echo ========================================
echo    网吧/电竞企业监控系统
echo ========================================
echo.

REM 检查是否安装了Python
python --version >nul 2>&1
if errorlevel 1 (
    echo ❌ 未检测到Python，正在打开下载页面...
    start https://www.python.org/downloads/
    pause
    exit
)

REM 检查是否安装了依赖
python -c "import flask" >nul 2>&1
if errorlevel 1 (
    echo 📦 正在安装依赖...
    python -m pip install -r requirements.txt
)

REM 启动应用
echo 🚀 正在启动Web服务...
python web_app.py

pause
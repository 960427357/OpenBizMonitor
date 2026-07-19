#!/bin/bash

echo ""
echo "========================================"
echo "   网吧/电竞企业监控系统"
echo "========================================"
echo ""

# 检查Python
if ! command -v python3 &> /dev/null; then
    echo "❌ 未检测到Python3，请先安装Python3"
    echo "   Ubuntu: sudo apt install python3 python3-pip python3-venv"
    exit 1
fi

echo "✅ Python3: $(python3 --version)"

# 检查并安装依赖
python3 -c "import flask" 2>/dev/null
if [ $? -ne 0 ]; then
    echo "📦 正在安装Python依赖..."
    pip3 install --user -r requirements.txt
fi

# 检查并安装Playwright
python3 -c "import playwright" 2>/dev/null
if [ $? -ne 0 ]; then
    echo "📦 正在安装Playwright..."
    pip3 install --user playwright
fi

# 检查Playwright浏览器是否已安装
if [ ! -d "$HOME/.cache/ms-playwright" ]; then
    echo "🌐 正在安装Playwright浏览器(Chromium)..."
    python3 -m playwright install chromium
fi

# 检查Linux系统依赖（仅在Linux上）
if [[ "$OSTYPE" == "linux-gnu"* ]]; then
    echo "🔍 检查Linux系统依赖..."
    MISSING_DEPS=""
    for pkg in libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 libcups2 \
               libdrm2 libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 \
               libxrandr2 libgbm1 libpango-1.0-0 libcairo2 libasound2 \
               libatspi2.0-0 libwayland-client0; do
        if ! dpkg -s "$pkg" &>/dev/null 2>&1; then
            MISSING_DEPS="$MISSING_DEPS $pkg"
        fi
    done
    if [ -n "$MISSING_DEPS" ]; then
        echo "⚠️  缺少系统依赖，尝试安装..."
        sudo apt-get update -qq
        sudo apt-get install -y -qq $MISSING_DEPS 2>/dev/null
        echo "✅ 系统依赖安装完成"
    else
        echo "✅ 系统依赖完整"
    fi
fi

# 确保logs目录存在
mkdir -p logs

# 获取本机IP
LOCAL_IP=$(hostname -I 2>/dev/null | awk '{print $1}')
if [ -z "$LOCAL_IP" ]; then
    LOCAL_IP=$(ip route get 1 2>/dev/null | awk '{print $7; exit}')
fi

echo ""
echo "🚀 正在启动Web服务..."
echo "========================================"
echo "  本地访问: http://localhost:8080"
echo "  局域网:   http://${LOCAL_IP:-<IP>}:8080"
echo ""
echo "  设置页面: http://localhost:8080/settings"
echo "  监控页面: http://localhost:8080/monitor"
echo "========================================"
echo ""
echo "💡 外网访问提示:"
echo "  - WSL2用户需在Windows执行端口转发:"
echo "    netsh interface portproxy add v4tov4 listenport=8080 listenaddress=0.0.0.0 connectport=8080 connectaddress=${LOCAL_IP}"
echo "  - 或在Windows防火墙放行8080端口"
echo "  - 云服务器需在安全组开放8080端口"
echo ""

# 启动应用
python3 web_app.py

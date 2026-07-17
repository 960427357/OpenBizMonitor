#!/bin/bash

echo ""
echo "========================================"
echo "   网吧/电竞企业监控系统"
echo "========================================"
echo ""

# 检查Python
if ! command -v python3 &> /dev/null; then
    echo "❌ 未检测到Python3，请先安装Python3"
    exit 1
fi

# 检查依赖
python3 -c "import flask" 2>/dev/null
if [ $? -ne 0 ]; then
    echo "📦 正在安装依赖..."
    pip3 install -r requirements.txt
fi

# 启动应用
echo "🚀 正在启动Web服务..."
python3 web_app.py
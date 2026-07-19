#!/bin/bash
# Ubuntu 22.04 一键部署脚本 (支持外网访问)
# 用法: chmod +x setup_ubuntu.sh && ./setup_ubuntu.sh

set -e

echo ""
echo "========================================"
echo "   网吧监控系统 - Ubuntu 部署脚本"
echo "========================================"
echo ""

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

info()  { echo -e "${GREEN}[INFO]${NC} $1"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; }

if [ "$EUID" -eq 0 ]; then
    warn "请不要使用root运行此脚本"
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/venv"

# 1. 系统依赖
info "更新系统包列表..."
sudo apt-get update -qq

info "安装系统依赖..."
sudo apt-get install -y -qq \
    python3 python3-pip python3-venv \
    libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 libcups2 \
    libdrm2 libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 \
    libxrandr2 libgbm1 libpango-1.0-0 libcairo2 libasound2 \
    libatspi2.0-0 libwayland-client0 wget gnupg2

# 2. 虚拟环境
if [ ! -d "$VENV_DIR" ]; then
    info "创建Python虚拟环境..."
    python3 -m venv "$VENV_DIR"
fi

source "$VENV_DIR/bin/activate"
info "虚拟环境: $(which python)"

# 3. Python依赖
info "安装Python依赖..."
pip install --upgrade pip -q
pip install -r "$SCRIPT_DIR/requirements.txt" -q
pip install playwright -q

# 4. Playwright浏览器
if [ ! -d "$HOME/.cache/ms-playwright" ]; then
    info "安装Playwright Chromium..."
    python3 -m playwright install chromium
    python3 -m playwright install-deps chromium 2>/dev/null || true
fi

# 5. 目录和权限
mkdir -p "$SCRIPT_DIR/logs"
chmod +x "$SCRIPT_DIR/start.sh"

# 6. 配置防火墙(开放8080端口)
info "配置防火墙..."
if command -v ufw &> /dev/null; then
    sudo ufw allow 8080/tcp 2>/dev/null || true
    info "已开放8080端口(ufw)"
fi

echo ""
echo "========================================"
info "部署完成!"
echo "========================================"

# 获取IP
LOCAL_IP=$(hostname -I 2>/dev/null | awk '{print $1}')

echo ""
echo "启动方式:"
echo "  source venv/bin/activate && python3 web_app.py"
echo ""
echo "访问地址:"
echo "  本地:     http://localhost:8080"
echo "  局域网:   http://${LOCAL_IP:-<IP>}:8080"
echo ""
echo "外网访问(WSL2):"
echo "  Windows管理员PowerShell执行:"
echo "  netsh interface portproxy add v4tov4 listenport=8080 listenaddress=0.0.0.0 connectport=8080 connectaddress=${LOCAL_IP}"
echo ""
echo "外网访问(云服务器/独立Linux):"
echo "  直接访问 http://<服务器公网IP>:8080"
echo "  需在云控制台安全组开放8080端口"
echo ""

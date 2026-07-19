# 网吧监控系统 v4.0 - 服务器部署指南

## v4.0 更新内容

- **多用户系统**：邀请码注册，每用户独立数据/配置/天眼查登录
- **批量操作**：批量选择、批量排除、批量修改状态、批量删除
- **数据字段完善**：新增电话、法人、资本、成立日期采集
- **企业名称可点击**：直接跳转天眼查查询
- **登录状态检查**：监控前自动检测天眼查登录状态
- **弹窗登录**：无需打开浏览器窗口，直接在网页扫码

## 系统要求

- **操作系统**: Ubuntu 22.04 LTS（推荐）/ 其他 Linux 发行版
- **内存**: >= 1GB
- **磁盘**: >= 2GB 可用空间
- **网络**: 需要访问 tianyancha.com

## 一、上传部署包

将 `OpenBizMonitor-deploy.zip` 上传到服务器：

```bash
# 方式1: scp
scp OpenBizMonitor-deploy.zip user@服务器IP:/home/user/

# 方式2: 通过宝塔/SFTP等工具上传
```

## 二、解压并部署

```bash
# 解压
cd /home/user
unzip OpenBizMonitor-deploy.zip -d OpenBizMonitor
cd OpenBizMonitor

# 运行一键部署脚本（首次）
chmod +x setup_ubuntu.sh
./setup_ubuntu.sh
```

部署脚本会自动完成：
1. 安装系统依赖（libnss3、libatk 等 Playwright 所需库）
2. 创建 Python 虚拟环境
3. 安装 Python 依赖（Flask、Playwright 等）
4. 下载 Playwright Chromium 浏览器
5. 开放 8080 端口防火墙

## 三、启动服务

```bash
cd /home/user/OpenBizMonitor

# 激活虚拟环境
source venv/bin/activate

# 启动
python3 web_app.py
```

启动后访问：
- 本地访问: http://localhost:8080
- 局域网访问: http://服务器IP:8080

## 四、后台运行（推荐）

### 方式1: nohup（简单）

```bash
source venv/bin/activate
nohup python3 web_app.py > /dev/null 2>&1 &
```

### 方式2: systemd 服务（推荐，开机自启）

```bash
# 创建服务文件
sudo tee /etc/systemd/system/bizmonitor.service << 'EOF'
[Unit]
Description=网吧监控系统
After=network.target

[Service]
Type=simple
User=user
WorkingDirectory=/home/user/OpenBizMonitor
ExecStart=/home/user/OpenBizMonitor/venv/bin/python3 web_app.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

# 启用并启动
sudo systemctl daemon-reload
sudo systemctl enable bizmonitor
sudo systemctl start bizmonitor

# 查看状态
sudo systemctl status bizmonitor

# 查看日志
sudo journalctl -u bizmonitor -f
```

## 五、首次登录天眼查

1. 浏览器打开 http://服务器IP:8080/settings
2. 点击 Playwright 浏览器状态的「检测」按钮，确认浏览器可用
3. 点击天眼查登录状态的「检测登录」按钮
4. 点击「登录」按钮，弹出二维码
5. 用天眼查 APP 扫码登录
6. 登录成功后状态自动更新为「已登录」

> 登录成功一次后，后续无需再次登录，cookies 自动保存。

## 六、外网访问配置

### WSL2 环境

在 Windows 管理员 PowerShell 中执行端口转发：

```powershell
netsh interface portproxy add v4tov4 listenport=8080 listenaddress=0.0.0.0 connectport=8080 connectaddress=WSL_IP
```

### 云服务器

1. 在云控制台安全组中开放 8080 端口
2. 直接通过 http://公网IP:8080 访问

### 局域网

确保防火墙已开放 8080 端口（`setup_ubuntu.sh` 已自动配置）。

## 七、配置说明

编辑 `config.json` 可修改端口等配置：

```json
{
  "web": {
    "port": 8080,
    "title": "网吧监控系统"
  }
}
```

修改后需重启服务生效。

## 八、常见问题

### Q: 二维码弹不出来 / 页面显示"操作存在异常"

天眼查有反爬检测。确保：
- `browser_manager.py` 中有 `add_init_script` 反检测脚本（已内置）
- 使用 Playwright 自带的 Chromium（不要用系统 Chrome 的旧版本）
- 清理 `browser_data/` 目录后重试

### Q: 登录成功但状态显示"未登录"

检查 `browser_data/` 目录是否有写入权限。登录成功后 cookies 保存在此目录。

### Q: 端口被占用

```bash
# 查找占用端口的进程
lsof -i :8080
# 终止进程
kill -9 <PID>
```

### Q: Playwright 浏览器未安装

```bash
source venv/bin/activate
python3 -m playwright install chromium
```

## 文件结构

```
OpenBizMonitor/
├── web_app.py              # Flask 主应用
├── browser_manager.py      # Playwright 浏览器管理（含反检测）
├── data_sources.py         # 数据源（天眼查网页爬取）
├── config_manager.py       # 配置管理
├── tianyancha_monitor.py   # 监控任务
├── templates/              # HTML 模板
│   ├── settings.html       # 设置页（含登录二维码弹窗）
│   └── monitor.html        # 监控页
├── static/                 # 静态资源
├── config.json             # 配置文件（首次运行自动生成）
├── database.json           # 数据库（首次运行自动生成）
├── browser_data/           # 浏览器数据（cookies等，自动生成）
├── logs/                   # 日志目录（自动生成）
├── requirements.txt        # Python 依赖
├── setup_ubuntu.sh         # 一键部署脚本
├── start.sh                # 启动脚本
└── DEPLOY.md               # 本文档
```

# OpenBizMonitor

企业监控系统 - 监控全国各地区的企业注册信息

## 功能

- 多数据源支持（天眼查、企查查）
- 自动监控企业注册信息
- 支持全国所有省市区县
- Tailwind CSS 现代化Web界面
- 深色模式
- JSON数据导出
- 多地区、多关键词筛选
- 排除关键词过滤

## 快速开始

### 环境要求

- Python 3.9+

### 安装

```bash
pip install -r requirements.txt
```

### 运行

```bash
python web_app.py
```

访问 http://localhost:8080

### 配置

首次运行后访问 http://localhost:8080/settings 进行配置：

1. 选择监控地区（省-市-区三级联动选择）
2. 配置搜索关键词（默认：网吧、网咖、电竞）
3. 配置数据源API Key（天眼查/企查查）
4. 保存配置

### 监控

在Web界面点击"开始监控"，或直接运行：

```bash
python tianyancha_monitor.py
```

## 目录结构

```
├── web_app.py              # Flask Web应用
├── tianyancha_monitor.py   # 监控脚本
├── config_manager.py       # 配置管理
├── data_sources.py         # 数据源抽象层（天眼查/企查查）
├── region_map.py           # 地区映射数据
├── requirements.txt        # 依赖
├── config.json             # 配置文件（自动生成）
├── database.json           # 数据库（自动生成）
├── templates/              # HTML模板
│   ├── base.html           # 共享布局
│   ├── index.html          # 数据列表页
│   ├── settings.html       # 设置页
│   └── monitor.html        # 监控页
├── static/                 # 静态资源
│   ├── app.js              # 前端逻辑
│   └── region-data.js      # 行政区划数据
└── README.md
```

## 数据源

### 天眼查

1. 访问 https://open.tianyancha.com/ 获取API Key
2. 在设置页面配置API Key

### 企查查

1. 获取企查查MCP API Key（Bearer Token）
2. 在设置页面配置API Key并启用
3. API地址默认为: `https://agent.qcc.com/mcp/company/stream`

## 技术栈

- 后端：Flask 3.0
- 前端：Tailwind CSS (CDN) + 原生JavaScript
- 数据存储：JSON文件
- Python依赖：Flask, Requests, openpyxl

## License

MIT License

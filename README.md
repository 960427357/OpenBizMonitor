# OpenBizMonitor

企业监控系统 - 监控全国各地区的企业注册信息

## 功能

- 🔍 自动监控企业注册信息
- 🌍 支持多地区监控
- 📊 Web界面管理
- 📈 数据可视化
- ⏰ 定时任务

## 快速开始

### 环境要求

- Python 3.7+
- Flask
- Requests

### 安装

```bash
pip install -r requirements.txt
```

### 配置

在 `config.json` 中配置：

```json
{
  "tianyancha": {
    "api_key": "你的API密钥"
  },
  "monitor": {
    "regions": ["四川省-南充市-顺庆区"],
    "keywords": ["网吧", "网咖"],
    "time_range": 1
  }
}
```

### 运行

```bash
python web_app.py
```

访问 http://localhost:8080

## 监控

运行监控脚本：

```bash
python tianyancha_monitor.py
```

## 目录结构

```
├── web_app.py              # Flask Web应用
├── tianyancha_monitor.py   # 监控脚本
├── config_manager.py       # 配置管理
├── requirements.txt        # 依赖
├── config.json            # 配置文件
├── database.json          # 数据库
├── templates/             # HTML模板
├── static/                # 静态资源
└── README.md              # 说明文档
```

## 待解决问题

### 当前问题：API不返回地址信息

**现象**：
- 搜索API返回的企业列表不包含 `regLocation` 字段
- 无法准确判断企业是否在监控地区内
- "南充市微米网咖"能被搜到，但无法确定地址

**测试结果**：
```python
# 搜索"南充市微米网咖"
返回：
{
  "name": "南充市微米网咖（个人独资）",
  "estiblishTime": "2026-04-14",
  "legalPersonName": "夏小银",
  "regLocation": ""  # 空！
}

# 搜索"网吧"
返回10条企业，所有企业的 regLocation 都为空
```

**需要解决的问题**：
1. 天眼查搜索API是否需要其他参数才能返回地址？
2. 是否需要调用其他API获取企业详情？
3. 是否有其他方式获取企业地址？

### 已知限制

- API搜索结果不包含地址信息
- 企业详情API工具名未知（`get_company_detail` 返回错误）
- 目前只能从企业名称推断地区（不够准确）

### 期望解决方案

欢迎提PR解决以下问题：

1. 查找正确的企业详情API
2. 优化地区提取逻辑
3. 添加其他数据源（企查查等）

## License

MIT License
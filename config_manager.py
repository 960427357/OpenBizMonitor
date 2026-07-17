# -*- coding: utf-8 -*-
"""
通用配置管理模块
支持配置加载、保存、数据库管理
"""

import json
import os
from datetime import datetime

class ConfigManager:
    """配置管理器"""

    def __init__(self, base_dir=None):
        """初始化配置管理器"""
        if base_dir is None:
            base_dir = os.path.dirname(__file__)

        self.config_path = os.path.join(base_dir, 'config.json')
        self.db_path = os.path.join(base_dir, 'database.json')

        self.default_config = {
            "tianyancha": {
                "api_url": "https://mcp.tianyancha.com/v1",
                "api_key": ""
            },
            "monitor": {
                "provinces": [],
                "cities": [],
                "keywords": ["网吧", "网咖", "电竞", "互联网服务"],
                "exclude_keywords": ["奶茶", "餐饮", "超市", "便利店"],
                "search_limit": 10
            },
            "notification": {
                "enabled": False,
                "wecom_webhook": "",
                "email_smtp": "",
                "email_from": "",
                "email_to": ""
            },
            "web": {
                "port": 8080,
                "title": "网吧监控系统"
            },
            "system": {
                "version": "2.0.0",
                "last_updated": ""
            }
        }

    def load_config(self):
        """加载配置文件"""
        if not os.path.exists(self.config_path):
            self.save_config(self.default_config)
            return self.default_config.copy()

        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
                # 合并默认配置
                merged = self.default_config.copy()
                merged.update(config)
                return merged
        except Exception as e:
            print(f"配置加载失败: {e}")
            return self.default_config.copy()

    def save_config(self, config):
        """保存配置文件"""
        # 确保system字段存在
        if 'system' not in config:
            config['system'] = {}
        config['system']['last_updated'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        try:
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            print(f"配置保存失败: {e}")
            return False

    def load_db(self):
        """加载数据库"""
        if not os.path.exists(self.db_path):
            return {
                "meta": {
                    "version": "1.0",
                    "total_records": 0
                },
                "records": []
            }

        try:
            with open(self.db_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"数据库加载失败: {e}")
            return {
                "meta": {"version": "1.0", "total_records": 0},
                "records": []
            }

    def save_db(self, data):
        """保存数据库"""
        data['meta']['total_records'] = len(data.get('records', []))
        try:
            with open(self.db_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            print(f"数据库保存失败: {e}")
            return False

    def add_record(self, record):
        """添加记录"""
        db = self.load_db()
        records = db.get('records', [])

        # 检查重复
        for existing in records:
            if existing.get('name') == record.get('name') and \
               existing.get('address', '') == record.get('address', ''):
                return False

        # 生成唯一ID
        import uuid
        record['id'] = str(uuid.uuid4())[:8]
        
        # 添加时间戳
        record['created_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        record['last_updated'] = datetime.now().strftime('%Y-%m-%d')

        records.append(record)
        return self.save_db(db)

    def get_db_path(self):
        """获取数据库路径"""
        return self.db_path


# 全局实例
config_mgr = ConfigManager()
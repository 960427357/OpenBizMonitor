# -*- coding: utf-8 -*-
"""
配置管理模块
支持配置加载、保存、数据库管理
"""

import json
import os
import sys
import uuid
import threading
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

_db_lock = threading.Lock()


class ConfigManager:
    """配置管理器"""

    def __init__(self, base_dir=None):
        if base_dir is None:
            # 打包后 exe 所在目录才是真正的根目录
            if getattr(sys, 'frozen', False):
                # PyInstaller 打包后，exe 在 _internal 的上一级目录
                base_dir = os.path.dirname(sys.executable)
            else:
                base_dir = os.path.dirname(__file__)

        self.config_path = os.path.join(base_dir, 'config.json')
        self.db_path = os.path.join(base_dir, 'database.json')

        self.default_config = {
            "tianyancha": {
                "api_url": "https://mcp.tianyancha.com/v1",
                "api_key": ""
            },
            "qichacha": {
                "api_url": "https://agent.qcc.com/mcp/company/stream",
                "api_key": ""
            },
            "datasource": {
                "active": ["tianyancha_web"]
            },
            "monitor": {
                "regions": [],
                "keywords": ["网吧", "网咖", "电竞", "互联网服务"],
                "exclude_keywords": ["奶茶", "餐饮", "超市", "便利店"],
                "time_range": 1
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
                "version": "3.0.0",
                "last_updated": ""
            }
        }

    def _deep_merge(self, base, override):
        """深度合并两个字典，override中的值覆盖base"""
        result = base.copy()
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = value
        return result

    def load_config(self):
        """加载配置文件"""
        if not os.path.exists(self.config_path):
            self.save_config(self.default_config)
            return self.default_config.copy()

        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
                return self._deep_merge(self.default_config, config)
        except Exception as e:
            logger.error("配置加载失败: %s", e)
            return self.default_config.copy()

    def save_config(self, config):
        """保存配置文件"""
        if 'system' not in config:
            config['system'] = {}
        config['system']['last_updated'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        try:
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            logger.error("配置保存失败: %s", e)
            return False

    def load_db(self):
        """加载数据库"""
        if not os.path.exists(self.db_path):
            return {
                "meta": {"version": "3.0", "total_records": 0, "last_updated": ""},
                "records": []
            }

        with _db_lock:
            try:
                with open(self.db_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.error("数据库加载失败: %s", e)
                return {
                    "meta": {"version": "3.0", "total_records": 0, "last_updated": ""},
                    "records": []
                }

    def save_db(self, data):
        """保存数据库"""
        with _db_lock:
            data['meta']['total_records'] = len(data.get('records', []))
            data['meta']['last_updated'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            try:
                with open(self.db_path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                return True
            except Exception as e:
                logger.error("数据库保存失败: %s", e)
                return False

    def add_record(self, record):
        """添加记录"""
        db = self.load_db()
        records = db.get('records', [])

        for existing in records:
            if existing.get('name') == record.get('name') and \
               existing.get('address', '') == record.get('address', ''):
                return False

        record['id'] = str(uuid.uuid4())[:8]
        record['created_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        record['last_updated'] = datetime.now().strftime('%Y-%m-%d')

        records.append(record)
        return self.save_db(db)

    def get_db_path(self):
        """获取数据库路径"""
        return self.db_path

    # ==================== 按用户隔离 ====================

    def _user_data_dir(self, user_id):
        """获取用户数据目录"""
        d = os.path.join(os.path.dirname(self.config_path), 'data', 'user_data', user_id)
        os.makedirs(d, exist_ok=True)
        return d

    def user_config_path(self, user_id):
        return os.path.join(self._user_data_dir(user_id), 'config.json')

    def user_db_path(self, user_id):
        return os.path.join(self._user_data_dir(user_id), 'database.json')

    def load_user_config(self, user_id):
        """加载用户配置，不存在则用默认值"""
        path = self.user_config_path(user_id)
        default = {
            "monitor": {
                "regions": [],
                "keywords": ["网吧", "网咖", "电竞", "互联网服务"],
                "exclude_keywords": ["奶茶", "餐饮", "超市", "便利店"],
                "time_range": 1
            }
        }
        if not os.path.exists(path):
            return default.copy()
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return self._deep_merge(default, json.load(f))
        except Exception:
            return default.copy()

    def save_user_config(self, user_id, config):
        """保存用户配置"""
        try:
            with open(self.user_config_path(user_id), 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            logger.error("保存用户配置失败: %s", e)
            return False

    def load_user_db(self, user_id):
        """加载用户数据库"""
        path = self.user_db_path(user_id)
        empty = {"meta": {"version": "3.0", "total_records": 0, "last_updated": ""}, "records": []}
        if not os.path.exists(path):
            return empty
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return empty

    def save_user_db(self, user_id, data):
        """保存用户数据库"""
        data['meta']['total_records'] = len(data.get('records', []))
        data['meta']['last_updated'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        try:
            with open(self.user_db_path(user_id), 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            logger.error("保存用户数据库失败: %s", e)
            return False

    def add_user_record(self, user_id, record):
        """添加用户记录（按 name+address 去重）"""
        db = self.load_user_db(user_id)
        for existing in db.get('records', []):
            if existing.get('name') == record.get('name') and \
               existing.get('address', '') == record.get('address', ''):
                return False
        record['id'] = str(uuid.uuid4())[:8]
        record['created_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        record['last_updated'] = datetime.now().strftime('%Y-%m-%d')
        db.setdefault('records', []).append(record)
        return self.save_user_db(user_id, db)


# 全局实例
config_mgr = ConfigManager()

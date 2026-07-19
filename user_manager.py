# -*- coding: utf-8 -*-
"""
用户管理模块
支持用户注册（邀请码）、登录、密码哈希
"""

import json
import os
import sys
import uuid
import hashlib
import secrets
import threading
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

_user_lock = threading.Lock()


def _hash_password(password, salt=None):
    """密码哈希 (PBKDF2-SHA256)"""
    if salt is None:
        salt = secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt.encode('utf-8'), 600000)
    return f"pbkdf2:sha256:600000${salt}${h.hex()}"


def _verify_password(password, stored_hash):
    """验证密码"""
    try:
        parts = stored_hash.split('$')
        salt = parts[1]
        return _hash_password(password, salt) == stored_hash
    except Exception:
        return False


class UserManager:
    """用户管理器"""

    def __init__(self, base_dir=None):
        if base_dir is None:
            if getattr(sys, 'frozen', False):
                base_dir = os.path.dirname(sys.executable)
            else:
                base_dir = os.path.dirname(__file__)

        self.data_dir = os.path.join(base_dir, 'data')
        self.users_path = os.path.join(self.data_dir, 'users.json')
        os.makedirs(self.data_dir, exist_ok=True)

    def _load(self):
        if not os.path.exists(self.users_path):
            return {"users": {}, "invite_codes": {}}
        try:
            with open(self.users_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error("加载用户数据失败: %s", e)
            return {"users": {}, "invite_codes": {}}

    def _save(self, data):
        with open(self.users_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def create_user(self, username, password, invite_code=None):
        """注册新用户"""
        with _user_lock:
            data = self._load()

            # 检查用户名唯一
            for u in data['users'].values():
                if u['username'] == username:
                    return None, "用户名已存在"

            # 验证邀请码（第一个用户不需要邀请码，自动成为管理员）
            is_first_user = len(data['users']) == 0
            if not is_first_user:
                if not invite_code:
                    return None, "需要邀请码"
                codes = data.get('invite_codes', {})
                code_info = codes.get(invite_code)
                if not code_info:
                    return None, "邀请码无效"
                if code_info.get('used', 0) >= code_info.get('max_uses', 1):
                    return None, "邀请码已用完"
                code_info['used'] = code_info.get('used', 0) + 1

            user_id = 'u_' + uuid.uuid4().hex[:12]
            user = {
                "id": user_id,
                "username": username,
                "password_hash": _hash_password(password),
                "role": "admin" if is_first_user else "user",
                "created_at": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            }
            data['users'][user_id] = user
            self._save(data)

            # 创建用户数据目录
            user_data_dir = os.path.join(self.data_dir, 'user_data', user_id)
            os.makedirs(user_data_dir, exist_ok=True)

            logger.info("用户注册成功: %s (role=%s)", username, user['role'])
            return user_id, None

    def authenticate(self, username, password):
        """验证登录"""
        data = self._load()
        for u in data['users'].values():
            if u['username'] == username:
                if _verify_password(password, u['password_hash']):
                    return u
                return None
        return None

    def get_user(self, user_id):
        """获取用户信息"""
        data = self._load()
        return data['users'].get(user_id)

    def get_user_by_username(self, username):
        """通过用户名获取"""
        data = self._load()
        for u in data['users'].values():
            if u['username'] == username:
                return u
        return None

    def list_users(self):
        """列出所有用户"""
        data = self._load()
        return list(data['users'].values())

    def generate_invite_code(self, max_uses=10):
        """生成邀请码"""
        with _user_lock:
            data = self._load()
            code = 'INV' + secrets.token_hex(4).upper()
            data.setdefault('invite_codes', {})[code] = {
                "max_uses": max_uses,
                "used": 0,
                "created_at": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
            self._save(data)
            return code

    def list_invite_codes(self):
        """列出所有邀请码"""
        data = self._load()
        codes = data.get('invite_codes', {})
        result = []
        for code, info in codes.items():
            result.append({
                "code": code,
                "max_uses": info.get('max_uses', 1),
                "used": info.get('used', 0),
                "created_at": info.get('created_at', '')
            })
        return result

    def delete_invite_code(self, code):
        """删除邀请码"""
        with _user_lock:
            data = self._load()
            codes = data.get('invite_codes', {})
            if code in codes:
                del codes[code]
                self._save(data)
                return True
            return False


# 全局实例
user_mgr = UserManager()

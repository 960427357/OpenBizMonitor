# -*- coding: utf-8 -*-
"""
认证中间件
Flask session-based 认证
"""

from functools import wraps
from flask import session, redirect, url_for, request, jsonify


def login_required(f):
    """登录验证装饰器"""
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            if request.path.startswith('/api/'):
                return jsonify({'error': '未登录'}), 401
            return redirect(url_for('login_page'))
        return f(*args, **kwargs)
    return decorated


def admin_required(f):
    """管理员验证装饰器"""
    @wraps(f)
    def decorated(*args, **kwargs):
        if session.get('role') != 'admin':
            if request.path.startswith('/api/'):
                return jsonify({'error': '需要管理员权限'}), 403
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated


def get_current_user_id():
    """获取当前登录用户ID"""
    return session.get('user_id')


def get_current_user():
    """获取当前登录用户信息"""
    from user_manager import user_mgr
    user_id = session.get('user_id')
    if user_id:
        return user_mgr.get_user(user_id)
    return None

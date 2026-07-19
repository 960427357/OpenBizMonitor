# -*- coding: utf-8 -*-
"""
网吧监控系统 - 主Web应用
"""

import sys
import io
import os
import time
import subprocess
from datetime import datetime

# 修复Windows控制台GBK编码不支持emoji的问题
if sys.platform == 'win32' and sys.stdout and sys.stdout.buffer:
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')
    except Exception:
        pass

from flask import Flask, render_template, request, jsonify, session, redirect, url_for

from log_config import setup_logging, get_logger
from config_manager import config_mgr
from user_manager import user_mgr
from auth import login_required, admin_required, get_current_user_id, get_current_user

logger = get_logger('web')

app = Flask(__name__)

# Flask session secret key
import secrets as _secrets
_config = config_mgr.load_config()
if not _config.get('system', {}).get('secret_key'):
    _config.setdefault('system', {})['secret_key'] = _secrets.token_hex(32)
    config_mgr.save_config(_config)
app.secret_key = _config['system']['secret_key']


@app.context_processor
def inject_user():
    """所有模板可使用 current_user 和 system_config"""
    sys_config = config_mgr.load_config()
    return dict(current_user=get_current_user(), system_config=sys_config)

if getattr(sys, 'frozen', False):
    # 打包后：exe所在目录用于存数据
    DATA_DIR = os.path.dirname(sys.executable)
    # onedir模式下模板/静态文件在 _internal 目录下
    _internal_dir = os.path.join(os.path.dirname(sys.executable), '_internal')
    RESOURCE_DIR = _internal_dir if os.path.exists(_internal_dir) else DATA_DIR
else:
    DATA_DIR = os.path.dirname(__file__)
    RESOURCE_DIR = os.path.dirname(__file__)

STATIC_DIR = os.path.join(RESOURCE_DIR, 'static')
TEMPLATE_DIR = os.path.join(RESOURCE_DIR, 'templates')

app.static_folder = STATIC_DIR
app.template_folder = TEMPLATE_DIR

# Playwright 浏览器管理
import browser_manager


# ==================== 请求日志中间件 ====================

@app.before_request
def log_request():
    request._start_time = time.time()


@app.after_request
def log_response(response):
    duration = (time.time() - getattr(request, '_start_time', 0)) * 1000
    if request.path.startswith('/api/'):
        logger.info("%s %s %s %.1fms", request.method, request.path, response.status_code, duration)
    return response


@app.errorhandler(Exception)
def handle_exception(e):
    logger.error("请求异常: %s %s - %s", request.method, request.path, str(e), exc_info=True)
    return jsonify({'error': str(e)}), 500


# ==================== 认证端点 ====================

@app.route('/login')
def login_page():
    if 'user_id' in session:
        return redirect(url_for('index'))
    return render_template('login.html')


@app.route('/register')
def register_page():
    if 'user_id' in session:
        return redirect(url_for('index'))
    return render_template('register.html')


@app.route('/api/auth/login', methods=['POST'])
def api_auth_login():
    data = request.json
    username = data.get('username', '').strip()
    password = data.get('password', '')
    if not username or not password:
        return jsonify({'success': False, 'error': '请输入用户名和密码'})
    user = user_mgr.authenticate(username, password)
    if user:
        session['user_id'] = user['id']
        session['username'] = user['username']
        session['role'] = user['role']
        logger.info("用户登录: %s", username)
        return jsonify({'success': True})
    return jsonify({'success': False, 'error': '用户名或密码错误'})


@app.route('/api/auth/register', methods=['POST'])
def api_auth_register():
    data = request.json
    username = data.get('username', '').strip()
    password = data.get('password', '')
    invite_code = data.get('invite_code', '').strip() or None
    if not username or not password:
        return jsonify({'success': False, 'error': '请输入用户名和密码'})
    if len(password) < 6:
        return jsonify({'success': False, 'error': '密码至少6位'})
    user_id, error = user_mgr.create_user(username, password, invite_code)
    if user_id:
        logger.info("用户注册: %s (id=%s)", username, user_id)
        return jsonify({'success': True})
    return jsonify({'success': False, 'error': error})


@app.route('/api/auth/logout', methods=['POST'])
def api_auth_logout():
    session.clear()
    return jsonify({'success': True})


@app.route('/api/auth/me')
def api_auth_me():
    user = get_current_user()
    if user:
        return jsonify({'logged_in': True, 'username': user['username'], 'role': user['role']})
    return jsonify({'logged_in': False})


@app.route('/api/admin/invite-codes', methods=['GET', 'POST'])
@login_required
@admin_required
def api_admin_invite_codes():
    if request.method == 'POST':
        data = request.json or {}
        max_uses = data.get('max_uses', 10)
        code = user_mgr.generate_invite_code(max_uses)
        return jsonify({'success': True, 'code': code})
    return jsonify(user_mgr.list_invite_codes())


@app.route('/api/admin/invite-codes', methods=['DELETE'])
@login_required
@admin_required
def api_admin_delete_invite_code():
    data = request.json or {}
    code = data.get('code', '')
    if user_mgr.delete_invite_code(code):
        return jsonify({'success': True})
    return jsonify({'success': False, 'error': '邀请码不存在'}), 404


@app.route('/api/admin/users')
@login_required
@admin_required
def api_admin_users():
    users = user_mgr.list_users()
    safe = []
    for u in users:
        safe.append({
            'id': u['id'],
            'username': u['username'],
            'role': u['role'],
            'created_at': u.get('created_at', '')
        })
    return jsonify(safe)


# ==================== 页面路由 ====================

@app.route('/admin')
@login_required
@admin_required
def admin_page():
    config = config_mgr.load_config()
    return render_template('admin.html', config=config)

@app.route('/')
def index():
    try:
        user_id = get_current_user_id()
        if user_id:
            config = config_mgr.load_user_config(user_id)
            db = config_mgr.load_user_db(user_id)
        else:
            config = config_mgr.load_config()
            db = {"records": []}
        records = db.get('records', [])

        stats = {'total': len(records), 'by_status': {}, 'by_area': {}, 'by_source': {}, 'recent': []}
        for r in records:
            stats['by_status'][r.get('status', '未知')] = stats['by_status'].get(r.get('status', '未知'), 0) + 1
            stats['by_area'][r.get('area', '未知')] = stats['by_area'].get(r.get('area', '未知'), 0) + 1
            stats['by_source'][r.get('source', '未知')] = stats['by_source'].get(r.get('source', '未知'), 0) + 1

        stats['recent'] = sorted(records, key=lambda x: x.get('last_updated', ''), reverse=True)[:10]

        def sort_key(x):
            return (1 if x.get('status') == '筹建审批中' else 0,
                    x.get('establish_date', '') or '0000-00-00')
        records_sorted = sorted(records, key=sort_key, reverse=True)

        return render_template('index.html', stats=stats, records=records_sorted, config=config)
    except Exception as e:
        logger.error("加载首页失败: %s", e, exc_info=True)
        raise

@app.route('/settings')
@login_required
def settings():
    user_id = get_current_user_id()
    sys_config = config_mgr.load_config()
    user_config = config_mgr.load_user_config(user_id)
    # 合并：用户配置覆盖系统配置
    config = {**sys_config, **user_config}
    config['monitor'] = {**sys_config.get('monitor', {}), **user_config.get('monitor', {})}
    return render_template('settings.html', config=config)

@app.route('/monitor')
@login_required
def monitor():
    user_id = get_current_user_id()
    sys_config = config_mgr.load_config()
    user_config = config_mgr.load_user_config(user_id)
    config = {**sys_config, **user_config}
    config['monitor'] = {**sys_config.get('monitor', {}), **user_config.get('monitor', {})}
    return render_template('monitor.html', config=config)


# ==================== API路由 ====================

@app.route('/api/config', methods=['GET', 'POST'])
@login_required
def api_config():
    user_id = get_current_user_id()
    if request.method == 'POST':
        new_config = request.json
        logger.info("保存用户配置: user=%s, keys=%s", user_id, list(new_config.keys()))
        config_mgr.save_user_config(user_id, new_config)
        return jsonify({'success': True, 'message': '配置保存成功'})
    else:
        config = config_mgr.load_user_config(user_id)
        return jsonify(config)


# ==================== 批量操作 API ====================

@app.route('/api/records/batch/exclude', methods=['POST'])
@login_required
def api_batch_exclude():
    """批量排除记录"""
    user_id = get_current_user_id()
    data = request.json or {}
    ids = data.get('ids', [])
    if not ids:
        return jsonify({'success': False, 'error': '未选择记录'})

    db = config_mgr.load_user_db(user_id)
    records = db.get('records', [])
    updated = 0
    for r in records:
        if r.get('id') in ids:
            r['status'] = '已排除'
            r['last_updated'] = datetime.now().strftime('%Y-%m-%d')
            updated += 1

    config_mgr.save_user_db(user_id, db)
    logger.info("用户 %s 批量排除: %d 条", user_id, updated)
    return jsonify({'success': True, 'updated': updated})


@app.route('/api/records/batch/status', methods=['POST'])
@login_required
def api_batch_status():
    """批量修改状态"""
    user_id = get_current_user_id()
    data = request.json or {}
    ids = data.get('ids', [])
    new_status = data.get('status', '')
    if not ids or not new_status:
        return jsonify({'success': False, 'error': '参数不完整'})

    db = config_mgr.load_user_db(user_id)
    records = db.get('records', [])
    updated = 0
    for r in records:
        if r.get('id') in ids:
            r['status'] = new_status
            r['last_updated'] = datetime.now().strftime('%Y-%m-%d')
            updated += 1

    config_mgr.save_user_db(user_id, db)
    logger.info("用户 %s 批量修改状态为 %s: %d 条", user_id, new_status, updated)
    return jsonify({'success': True, 'updated': updated})


@app.route('/api/records/batch/delete', methods=['POST'])
@login_required
def api_batch_delete():
    """批量删除记录"""
    user_id = get_current_user_id()
    data = request.json or {}
    ids = data.get('ids', [])
    if not ids:
        return jsonify({'success': False, 'error': '未选择记录'})

    db = config_mgr.load_user_db(user_id)
    records = db.get('records', [])
    db['records'] = [r for r in records if r.get('id') not in ids]
    deleted = len(records) - len(db['records'])
    config_mgr.save_user_db(user_id, db)
    logger.info("用户 %s 批量删除: %d 条", user_id, deleted)
    return jsonify({'success': True, 'deleted': deleted})


# /api/records/clear 必须在 /api/records/<record_id> 之前定义
@app.route('/api/records/clear', methods=['DELETE'])
@login_required
def api_clear_all_records():
    try:
        user_id = get_current_user_id()
        db = config_mgr.load_user_db(user_id)
        count = len(db.get('records', []))
        db['records'] = []
        db['meta']['total_records'] = 0
        db['meta']['last_updated'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        result = config_mgr.save_user_db(user_id, db)
        if result:
            logger.info("用户 %s 清除数据: 删除了 %d 条记录", user_id, count)
            return jsonify({'success': True, 'message': '所有数据已清除'})
        else:
            return jsonify({'success': False, 'message': '保存失败'}), 500
    except Exception as e:
        logger.error("清除数据异常: %s", e, exc_info=True)
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/records', methods=['GET', 'POST'])
@login_required
def api_records():
    user_id = get_current_user_id()
    if request.method == 'POST':
        data = request.json
        data['id'] = f"NB-{int(time.time())}"
        data['status'] = data.get('status', '筹建审批中')
        data['source'] = data.get('source', '手动添加')
        if config_mgr.add_user_record(user_id, data):
            logger.info("用户 %s 新增记录: %s (id=%s)", user_id, data.get('name'), data['id'])
            return jsonify({'success': True, 'message': '添加成功', 'id': data['id']})
        return jsonify({'error': '企业已存在'}), 400

    db = config_mgr.load_user_db(user_id)
    return jsonify(db)

@app.route('/api/records/<record_id>', methods=['GET', 'PUT', 'DELETE'])
@login_required
def api_record_detail(record_id):
    user_id = get_current_user_id()
    db = config_mgr.load_user_db(user_id)
    records = db.get('records', [])

    if request.method == 'GET':
        for r in records:
            if r.get('id') == record_id:
                return jsonify(r)
        return jsonify({'error': 'Not found'}), 404

    elif request.method == 'PUT':
        data = request.json
        for i, r in enumerate(records):
            if r.get('id') == record_id:
                records[i].update(data)
                records[i]['last_updated'] = datetime.now().strftime('%Y-%m-%d')
                config_mgr.save_user_db(user_id, db)
                return jsonify({'success': True, 'message': '更新成功'})
        return jsonify({'error': 'Not found'}), 404

    elif request.method == 'DELETE':
        for i, r in enumerate(records):
            if r.get('id') == record_id:
                records.pop(i)
                config_mgr.save_user_db(user_id, db)
                return jsonify({'success': True, 'message': '删除成功'})
        return jsonify({'error': 'Not found'}), 404

@app.route('/api/records/<record_id>/exclude', methods=['POST'])
@login_required
def api_exclude_record(record_id):
    user_id = get_current_user_id()
    db = config_mgr.load_user_db(user_id)
    records = db.get('records', [])

    for r in records:
        if r.get('id') == record_id:
            r['status'] = '已排除'
            r['last_updated'] = datetime.now().strftime('%Y-%m-%d')
            config_mgr.save_user_db(user_id, db)
            return jsonify({'success': True, 'message': '已排除'})
    return jsonify({'error': 'Not found'}), 404

@app.route('/api/search')
def api_search():
    user_id = get_current_user_id()
    if not user_id:
        return jsonify([])
    query = request.args.get('q', '').lower()
    area = request.args.get('area', '')
    status = request.args.get('status', '')
    source = request.args.get('source', '')

    db = config_mgr.load_user_db(user_id)
    records = db.get('records', [])

    if query:
        records = [r for r in records if
                   query in r.get('name', '').lower() or
                   query in r.get('address', '').lower() or
                   query in r.get('legal_person', '').lower()]
    if area:
        records = [r for r in records if r.get('area') == area]
    if status:
        records = [r for r in records if r.get('status') == status]
    if source:
        records = [r for r in records if r.get('source') == source]

    records = sorted(records, key=lambda x: (1 if x.get('status') == '筹建审批中' else 0,
                                             x.get('establish_date', '') or '0000-00-00'), reverse=True)

    logger.debug("搜索: q=%s, area=%s, status=%s, 结果=%d", query, area, status, len(records))
    return jsonify(records)

# 监控进程状态（按用户隔离）
_monitor_processes = {}  # user_id -> Popen


def _get_monitor_output_file(user_id):
    log_dir = os.path.join(DATA_DIR, 'logs')
    os.makedirs(log_dir, exist_ok=True)
    return os.path.join(log_dir, f'monitor_{user_id}.log')


@app.route('/api/monitor/start', methods=['POST'])
@login_required
def api_monitor_start():
    user_id = get_current_user_id()

    # 检查是否已在运行
    if user_id in _monitor_processes and _monitor_processes[user_id].poll() is None:
        return jsonify({'success': False, 'error': '监控任务正在运行中，请等待完成'}), 409

    output_file = _get_monitor_output_file(user_id)
    logger.info("用户 %s 启动监控任务", user_id)
    try:
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(f"监控启动中...\n")

        import sys
        python_exe = sys.executable

        _monitor_processes[user_id] = subprocess.Popen(
            [python_exe, 'tianyancha_monitor.py', '--user-id', user_id],
            stdout=open(output_file, 'a', encoding='utf-8'),
            stderr=subprocess.STDOUT,
            cwd=DATA_DIR
        )
        logger.info("监控进程已启动: user=%s, pid=%d", user_id, _monitor_processes[user_id].pid)
        return jsonify({'success': True, 'message': '监控已启动', 'pid': _monitor_processes[user_id].pid})
    except Exception as e:
        logger.error("启动监控失败: %s", e, exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/monitor/status')
@login_required
def api_monitor_status():
    """查询当前用户的监控运行状态"""
    user_id = get_current_user_id()
    output_file = _get_monitor_output_file(user_id)
    proc = _monitor_processes.get(user_id)

    if proc is None or proc.poll() is not None:
        output = ''
        if os.path.exists(output_file):
            with open(output_file, 'r', encoding='utf-8') as f:
                output = f.read()
        return jsonify({'running': False, 'output': output, 'returncode': proc.returncode if proc else None})

    output = ''
    if os.path.exists(output_file):
        with open(output_file, 'r', encoding='utf-8') as f:
            content = f.read()
            output = content[-5000:] if len(content) > 5000 else content

    return jsonify({'running': True, 'output': output, 'pid': proc.pid})

@app.route('/api/export/json')
@app.route('/api/export')
@login_required
def api_export_json():
    user_id = get_current_user_id()
    return jsonify(config_mgr.load_user_db(user_id))


@app.route('/api/check-browser')
@login_required
def api_check_browser():
    """检测 Playwright 浏览器状态"""
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            browser.close()
        return jsonify({'connected': True, 'version': 'playwright'})
    except Exception as e:
        return jsonify({'connected': False, 'error': str(e)})


@app.route('/api/check-tianyancha-login')
@login_required
def api_check_tianyancha_login():
    """检测天眼查登录状态"""
    user_id = get_current_user_id()
    try:
        logged_in = browser_manager.is_logged_in_for_user(user_id)
        if logged_in:
            return jsonify({'logged_in': True, 'username': '已登录用户'})
        else:
            return jsonify({'logged_in': False, 'message': '未登录，请点击"登录"按钮扫码登录'})
    except Exception as e:
        return jsonify({'logged_in': False, 'error': str(e)})


@app.route('/api/tianyancha-login', methods=['POST'])
@login_required
def api_tianyancha_login():
    """打开浏览器让用户扫码登录天眼查"""
    try:
        success = browser_manager.login_interactive()
        if success:
            return jsonify({'success': True, 'message': '登录成功'})
        else:
            return jsonify({'success': False, 'error': '登录失败或超时'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/tianyancha-login-start', methods=['POST'])
@login_required
def api_tianyancha_login_start():
    """启动二维码登录会话，返回二维码图片"""
    user_id = get_current_user_id()
    try:
        result = browser_manager.qr_login_start_for_user(user_id)
        if result and result.get('qr_image'):
            return jsonify({'success': True, 'qr_image': result['qr_image']})
        else:
            return jsonify({'success': False, 'error': result.get('error', '无法获取二维码')}), 500
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/tianyancha-login-qr-status')
@login_required
def api_tianyancha_login_qr_status():
    """轮询二维码登录状态"""
    user_id = get_current_user_id()
    try:
        result = browser_manager.qr_login_poll_for_user(user_id)
        return jsonify(result)
    except Exception as e:
        return jsonify({'status': 'error', 'error': str(e)}), 500


@app.route('/api/tianyancha-login-cleanup', methods=['POST'])
@login_required
def api_tianyancha_login_cleanup():
    """清理二维码登录会话"""
    user_id = get_current_user_id()
    try:
        browser_manager.qr_login_cleanup_for_user(user_id)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ==================== 主程序 ====================

def main():
    setup_logging()

    config = config_mgr.load_config()
    port = config.get('web', {}).get('port', 8080)
    title = config.get('web', {}).get('title', '网吧监控系统')

    logger.info("启动 %s - 端口 %d", title, port)
    logger.info("数据库: %s", config_mgr.get_db_path())

    print(f"""
{'='*60}
{title}
{'='*60}
数据库: {config_mgr.get_db_path()}
日志文件: logs/app.log
访问地址: http://localhost:{port}
设置页面: http://localhost:{port}/settings
监控页面: http://localhost:{port}/monitor
{'='*60}
    """)

    # 启动后自动打开浏览器
    import threading
    import webbrowser

    def open_browser():
        """延迟2秒后打开浏览器（WSL/SSH等无头环境跳过）"""
        import time
        time.sleep(2)
        # 无头环境不尝试打开浏览器
        if not os.environ.get('DISPLAY') and sys.platform != 'win32':
            logger.info("无图形环境，跳过自动打开浏览器")
            return
        try:
            webbrowser.open(f'http://localhost:{port}')
            logger.info("自动打开浏览器: http://localhost:%d", port)
        except Exception as e:
            logger.warning("自动打开浏览器失败: %s", e)

    threading.Thread(target=open_browser, daemon=True).start()

    try:
        app.run(host='0.0.0.0', port=port, debug=False, threaded=True)
    finally:
        # 确保浏览器资源释放
        try:
            browser_manager.close_browser()
        except Exception:
            pass


if __name__ == '__main__':
    main()

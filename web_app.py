# -*- coding: utf-8 -*-
"""
通用网吧监控系统 - 主Web应用
"""

from flask import Flask, render_template, request, jsonify, send_from_directory
import os
import json
import time
import subprocess
from datetime import datetime

from config_manager import config_mgr

app = Flask(__name__)

# 设置路径
BASE_DIR = os.path.dirname(__file__)
STATIC_DIR = os.path.join(BASE_DIR, 'static')
TEMPLATE_DIR = os.path.join(BASE_DIR, 'templates')

app.static_folder = STATIC_DIR
app.template_folder = TEMPLATE_DIR

# ==================== 页面路由 ====================

@app.route('/')
def index():
    """主页"""
    config = config_mgr.load_config()
    db = config_mgr.load_db()
    records = db.get('records', [])

    # 统计
    stats = {'total': len(records), 'by_status': {}, 'by_area': {}, 'by_source': {}, 'recent': []}
    for r in records:
        stats['by_status'][r.get('status', '未知')] = stats['by_status'].get(r.get('status', '未知'), 0) + 1
        stats['by_area'][r.get('area', '未知')] = stats['by_area'].get(r.get('area', '未知'), 0) + 1
        stats['by_source'][r.get('source', '未知')] = stats['by_source'].get(r.get('source', '未知'), 0) + 1

    stats['recent'] = sorted(records, key=lambda x: x.get('last_updated', ''), reverse=True)[:10]

    # 排序
    def sort_key(x):
        return (1 if x.get('status') == '筹建审批中' else 0,
                x.get('establish_date', '') or '0000-00-00')
    records_sorted = sorted(records, key=sort_key, reverse=True)

    return render_template('index.html', stats=stats, records=records_sorted, config=config)

@app.route('/settings')
def settings():
    """设置页面"""
    config = config_mgr.load_config()
    return render_template('settings.html', config=config)

@app.route('/monitor')
def monitor():
    """监控页面"""
    config = config_mgr.load_config()
    return render_template('monitor.html', config=config)

# ==================== API路由 ====================

@app.route('/api/config', methods=['GET', 'POST'])
def api_config():
    """配置API"""
    if request.method == 'POST':
        config = request.json
        config_mgr.save_config(config)
        return jsonify({'success': True, 'message': '配置保存成功'})
    else:
        config = config_mgr.load_config()
        # 隐藏敏感信息
        safe_config = config.copy()
        if 'tianyancha' in safe_config:
            safe_config['tianyancha']['api_key'] = '***' if safe_config['tianyancha'].get('api_key') else ''
        return jsonify(safe_config)

@app.route('/api/records', methods=['GET', 'POST'])
def api_records():
    """记录API"""
    if request.method == 'POST':
        data = request.json
        data['id'] = f"NB-{int(time.time())}"
        data['status'] = data.get('status', '筹建审批中')
        data['source'] = data.get('source', '手动添加')
        if config_mgr.add_record(data):
            return jsonify({'success': True, 'message': '添加成功', 'id': data['id']})
        return jsonify({'error': '企业已存在'}), 400

    db = config_mgr.load_db()
    return jsonify(db)

@app.route('/api/records/<record_id>', methods=['GET', 'PUT', 'DELETE'])
def api_record_detail(record_id):
    """单条记录"""
    db = config_mgr.load_db()
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
                config_mgr.save_db(db)
                return jsonify({'success': True, 'message': '更新成功'})
        return jsonify({'error': 'Not found'}), 404

    elif request.method == 'DELETE':
        for i, r in enumerate(records):
            if r.get('id') == record_id:
                records.pop(i)
                config_mgr.save_db(db)
                return jsonify({'success': True, 'message': '删除成功'})
        return jsonify({'error': 'Not found'}), 404

@app.route('/api/records/<record_id>/exclude', methods=['POST'])
def api_exclude_record(record_id):
    """标记排除"""
    db = config_mgr.load_db()
    records = db.get('records', [])

    for r in records:
        if r.get('id') == record_id:
            r['status'] = '已排除'
            r['last_updated'] = datetime.now().strftime('%Y-%m-%d')
            config_mgr.save_db(db)
            return jsonify({'success': True, 'message': '已排除'})
    return jsonify({'error': 'Not found'}), 404

@app.route('/api/records/clear', methods=['DELETE'])
def api_clear_all_records():
    """清除所有数据"""
    try:
        db = config_mgr.load_db()
        db['records'] = []
        db['meta']['total_records'] = 0
        db['meta']['last_updated'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        result = config_mgr.save_db(db)
        if result:
            return jsonify({'success': True, 'message': '所有数据已清除'})
        else:
            return jsonify({'success': False, 'message': '保存失败'}), 500
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/search')
def api_search():
    """搜索"""
    query = request.args.get('q', '').lower()
    area = request.args.get('area', '')
    status = request.args.get('status', '')
    source = request.args.get('source', '')

    db = config_mgr.load_db()
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

    # 排序
    records = sorted(records, key=lambda x: (1 if x.get('status') == '筹建审批中' else 0,
                                             x.get('establish_date', '') or '0000-00-00'), reverse=True)

    return jsonify(records)

@app.route('/api/monitor/start', methods=['POST'])
def api_monitor_start():
    """启动监控"""
    try:
        result = subprocess.run(['python', 'tianyancha_monitor.py'],
                              capture_output=True, text=True, timeout=300, cwd=BASE_DIR)
        return jsonify({'success': True, 'output': result.stdout, 'error': result.stderr})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/export/json')
def api_export_json():
    """导出"""
    return jsonify(config_mgr.load_db())

# ==================== 主程序 ====================

def main():
    """启动"""
    config = config_mgr.load_config()
    port = config.get('web', {}).get('port', 8080)
    title = config.get('web', {}).get('title', '网吧监控系统')

    print(f"""
{'='*60}
🎮 {title}
{'='*60}
📊 数据库: {config_mgr.get_db_path()}
🌐 访问地址: http://localhost:{port}
📌 设置页面: http://localhost:{port}/settings
🔍 监控页面: http://localhost:{port}/monitor
{'='*60}
    """)

    # 自动打开浏览器
    try:
        import webbrowser
        webbrowser.open(f'http://localhost:{port}')
    except:
        pass

    app.run(host='0.0.0.0', port=port, debug=False)

if __name__ == '__main__':
    main()
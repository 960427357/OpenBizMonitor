# -*- coding: utf-8 -*-
"""
打包为EXE的辅助脚本
"""

import os
import subprocess
import sys

def build_exe():
    """打包为EXE"""
    print("开始打包...")

    # 安装pyinstaller
    subprocess.run([sys.executable, '-m', 'pip', 'install', 'pyinstaller'], check=True)

    # 运行pyinstaller
    subprocess.run([
        sys.executable, '-m', 'PyInstaller',
        '--onefile',
        '--add-data', 'templates;templates',
        '--add-data', 'static;static',
        '--hidden-import', 'flask',
        '--hidden-import', 'jinja2',
        '--hidden-import', 'werkzeug',
        '--hidden-import', 'requests',
        'web_app.py'
    ], check=True)

    print("\n✅ 打包完成！")
    print("📁 EXE文件位置: dist/netbar-monitor.exe")

if __name__ == '__main__':
    build_exe()
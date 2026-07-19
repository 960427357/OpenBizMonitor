# -*- coding: utf-8 -*-
"""
Playwright 无头浏览器管理模块
替代 opencli 实现后台爬取天眼查网页
"""

import os
import sys
import logging
import asyncio
from pathlib import Path

logger = logging.getLogger(__name__)

# 打包后 exe 所在目录才是真正的根目录
if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(__file__)

# 设置 Playwright 浏览器路径（使用用户目录下安装的浏览器）
if 'PLAYWRIGHT_BROWSERS_PATH' not in os.environ:
    os.environ['PLAYWRIGHT_BROWSERS_PATH'] = os.path.join(os.path.expanduser('~'), '.cache', 'ms-playwright')

# 浏览器数据目录（保存 cookies/session）
BROWSER_DATA_DIR = os.path.join(BASE_DIR, 'browser_data')

# 全局浏览器实例（保留向后兼容）
_playwright = None
_browser = None
_context = None

# 按用户隔离的浏览器实例
_user_contexts = {}  # user_id -> {playwright, context}
_global_browser_lock = None  # 延迟初始化的 threading.Lock

# 二维码登录会话状态（按用户隔离）
_login_sessions = {}  # user_id -> {page, context, playwright, started_at}
_login_loop = None     # 专用后台 event loop
_login_loop_thread = None


def _get_data_dir():
    """获取浏览器数据目录"""
    os.makedirs(BROWSER_DATA_DIR, exist_ok=True)
    return BROWSER_DATA_DIR


def _get_user_data_dir(user_id):
    """获取用户浏览器数据目录"""
    d = os.path.join(BASE_DIR, 'data', 'user_data', user_id, 'browser_data')
    os.makedirs(d, exist_ok=True)
    return d


def _ensure_global_lock():
    """确保全局浏览器锁已初始化"""
    global _global_browser_lock
    if _global_browser_lock is None:
        import threading
        _global_browser_lock = threading.Lock()
    return _global_browser_lock


def _ensure_login_loop():
    """确保后台登录 event loop 正在运行"""
    global _login_loop, _login_loop_thread
    if _login_loop is not None and _login_loop.is_running():
        return _login_loop
    import threading
    _login_loop = asyncio.new_event_loop()
    _login_loop_thread = threading.Thread(target=_login_loop.run_forever, daemon=True)
    _login_loop_thread.start()
    return _login_loop


def _login_submit(coro):
    """向后台登录 loop 提交协程并阻塞等待结果"""
    loop = _ensure_login_loop()
    future = asyncio.run_coroutine_threadsafe(coro, loop)
    return future.result(timeout=300)


async def _init_async():
    """初始化 Playwright（异步）"""
    global _playwright, _browser, _context

    if _context is not None:
        return _context

    from playwright.async_api import async_playwright

    _playwright = await async_playwright().start()

    data_dir = _get_data_dir()

    # 查找系统浏览器可执行文件
    import glob
    if sys.platform == 'win32':
        edge_paths = glob.glob(r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe') + \
                     glob.glob(r'C:\Program Files\Microsoft\Edge\Application\msedge.exe')
        chrome_paths = glob.glob(r'C:\Program Files\Google\Chrome\Application\chrome.exe') + \
                       glob.glob(r'C:\Program Files (x86)\Google\Chrome\Application\chrome.exe')
    else:
        edge_paths = glob.glob('/usr/bin/microsoft-edge*') + \
                     glob.glob('/opt/microsoft/msedge/msedge')
        chrome_paths = glob.glob('/usr/bin/google-chrome*') + \
                       glob.glob('/usr/bin/chromium-browser') + \
                       glob.glob('/snap/bin/chromium') + \
                       glob.glob('/usr/bin/chromium')

    # 尝试 Edge
    if edge_paths:
        try:
            _context = await _playwright.chromium.launch_persistent_context(
                user_data_dir=data_dir,
                executable_path=edge_paths[0],
                headless=True,
                viewport={'width': 1920, 'height': 1080},
                locale='zh-CN',
                timezone_id='Asia/Shanghai',
                user_agent='Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--no-sandbox',
                    '--disable-dev-shm-usage',
                ],
                ignore_default_args=['--enable-automation'],
            )
            logger.info("使用系统 Edge 浏览器 (headless)")
            return _context
        except Exception as e:
            logger.debug("Edge 不可用: %s", e)

    # 尝试 Chrome
    if chrome_paths:
        try:
            _context = await _playwright.chromium.launch_persistent_context(
                user_data_dir=data_dir,
                executable_path=chrome_paths[0],
                headless=True,
                viewport={'width': 1920, 'height': 1080},
                locale='zh-CN',
                timezone_id='Asia/Shanghai',
                user_agent='Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--no-sandbox',
                    '--disable-dev-shm-usage',
                ],
                ignore_default_args=['--enable-automation'],
            )
            logger.info("使用系统 Chrome 浏览器 (headless)")
            return _context
        except Exception as e:
            logger.debug("Chrome 不可用: %s", e)

    # 最后尝试 Playwright 内置浏览器
    try:
        _context = await _playwright.chromium.launch_persistent_context(
            user_data_dir=data_dir,
            headless=True,
            viewport={'width': 1920, 'height': 1080},
            locale='zh-CN',
            timezone_id='Asia/Shanghai',
            user_agent='Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
            args=[
                '--disable-blink-features=AutomationControlled',
                '--no-sandbox',
                '--disable-dev-shm-usage',
            ],
            ignore_default_args=['--enable-automation'],
        )
        logger.info("使用 Playwright 内置浏览器 (headless)")
        return _context
    except Exception as e:
        error_msg = str(e)
        if "Executable doesn't exist" in error_msg:
            logger.warning("Playwright 浏览器未安装，正在自动安装...")
            print("首次运行，正在安装 Playwright 浏览器，请稍候...")
            try:
                import subprocess
                result = subprocess.run(
                    [sys.executable, '-m', 'playwright', 'install'],
                    capture_output=True,
                    text=True,
                    timeout=600
                )
                if result.returncode == 0:
                    print("浏览器安装完成！正在启动...")
                    _context = await _playwright.chromium.launch_persistent_context(
                        user_data_dir=data_dir,
                        headless=True,
                        viewport={'width': 1280, 'height': 800},
                        locale='zh-CN',
                        timezone_id='Asia/Shanghai',
                        args=[
                            '--disable-blink-features=AutomationControlled',
                            '--no-sandbox',
                        ]
                    )
                    return _context
            except Exception as install_err:
                logger.error("浏览器安装失败: %s", install_err)
        if sys.platform == 'win32':
            raise Exception("无法启动浏览器，请运行 fix_playwright.bat 修复")
        else:
            raise Exception("无法启动浏览器，请运行: python3 -m playwright install chromium")


async def _close_async():
    """关闭 Playwright（异步）"""
    global _playwright, _browser, _context

    if _context:
        await _context.close()
        _context = None
    if _playwright:
        await _playwright.stop()
        _playwright = None

    logger.info("Playwright 浏览器已关闭")


def _run_async(coro):
    """在同步环境中运行异步代码"""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # 如果已有事件循环在运行，创建新的线程执行
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                return pool.submit(asyncio.run, coro).result()
        else:
            return loop.run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)


# ==================== 按用户隔离的浏览器函数 ====================

async def _init_user_async(user_id):
    """为指定用户初始化 Playwright 浏览器上下文"""
    global _user_contexts

    if user_id in _user_contexts and _user_contexts[user_id].get('context'):
        return _user_contexts[user_id]['context']

    from playwright.async_api import async_playwright
    pw = await async_playwright().start()
    data_dir = _get_user_data_dir(user_id)

    context = None
    # 查找系统浏览器
    import glob
    if sys.platform == 'win32':
        candidates = glob.glob(r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe') + \
                     glob.glob(r'C:\Program Files\Microsoft\Edge\Application\msedge.exe') + \
                     glob.glob(r'C:\Program Files\Google\Chrome\Application\chrome.exe') + \
                     glob.glob(r'C:\Program Files (x86)\Google\Chrome\Application\chrome.exe')
    else:
        candidates = glob.glob('/usr/bin/microsoft-edge*') + \
                     glob.glob('/opt/microsoft/msedge/msedge') + \
                     glob.glob('/usr/bin/google-chrome*') + \
                     glob.glob('/usr/bin/chromium-browser') + \
                     glob.glob('/snap/bin/chromium') + \
                     glob.glob('/usr/bin/chromium')

    launch_args = [
        '--disable-blink-features=AutomationControlled',
        '--no-sandbox',
        '--disable-dev-shm-usage',
    ]

    for exe in candidates:
        try:
            context = await pw.chromium.launch_persistent_context(
                user_data_dir=data_dir,
                executable_path=exe,
                headless=True,
                viewport={'width': 1920, 'height': 1080},
                locale='zh-CN',
                timezone_id='Asia/Shanghai',
                user_agent='Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
                args=launch_args,
                ignore_default_args=['--enable-automation'],
            )
            break
        except Exception:
            continue

    if context is None:
        context = await pw.chromium.launch_persistent_context(
            user_data_dir=data_dir,
            headless=True,
            viewport={'width': 1920, 'height': 1080},
            locale='zh-CN',
            timezone_id='Asia/Shanghai',
            user_agent='Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
            args=launch_args,
            ignore_default_args=['--enable-automation'],
        )

    _user_contexts[user_id] = {'playwright': pw, 'context': context}
    return context


async def _close_user_async(user_id):
    """关闭指定用户的浏览器上下文"""
    global _user_contexts
    info = _user_contexts.pop(user_id, None)
    if info:
        try:
            await info['context'].close()
        except Exception:
            pass
        try:
            await info['playwright'].stop()
        except Exception:
            pass


async def _get_page_content_for_user_async(user_id, url, timeout=30000):
    """为指定用户获取页面内容"""
    context = await _init_user_async(user_id)
    page = await context.new_page()
    try:
        await page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            delete navigator.__proto__.webdriver;
            window.chrome = { runtime: {}, loadTimes: function(){}, csi: function(){}, app: {} };
            Object.defineProperty(navigator, 'plugins', {
                get: () => [
                    {description: "Portable Document Format", filename: "internal-pdf-viewer", length: 1, name: "Chrome PDF Plugin"},
                    {description: "", filename: "mhjfbmdgcfjbbpaeojofohoefgiehjai", length: 1, name: "Chrome PDF Viewer"},
                    {description: "", filename: "internal-nacl-plugin", length: 2, name: "Native Client"}
                ]
            });
            Object.defineProperty(navigator, 'languages', {get: () => ['zh-CN', 'zh', 'en-US', 'en']});
        """)
        await page.goto(url, wait_until='domcontentloaded', timeout=timeout)
        # 等待页面JS渲染完成 - 尝试等待搜索结果元素出现
        try:
            await page.wait_for_selector('a[href*="/company/"]', timeout=20000)
        except Exception:
            # 如果没找到，再等5秒让JS完成
            await page.wait_for_timeout(5000)
        # 额外等待确保内容完全渲染
        await page.wait_for_timeout(3000)
        # 使用page.content()获取完整渲染后的DOM
        content = await page.content()
        logger.info("页面加载完成 (user=%s): %s (%d bytes)", user_id, url, len(content))
        return content
    except Exception as e:
        logger.error("获取页面失败 (user=%s): %s", user_id, e)
        return None
    finally:
        await page.close()


async def _is_logged_in_for_user_async(user_id):
    """为指定用户检测天眼查登录状态"""
    try:
        context = await _init_user_async(user_id)
        page = await context.new_page()
        await page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            delete navigator.__proto__.webdriver;
            window.chrome = { runtime: {}, loadTimes: function(){}, csi: function(){}, app: {} };
            Object.defineProperty(navigator, 'plugins', {
                get: () => [
                    {description: "Portable Document Format", filename: "internal-pdf-viewer", length: 1, name: "Chrome PDF Plugin"},
                    {description: "", filename: "mhjfbmdgcfjbbpaeojofohoefgiehjai", length: 1, name: "Chrome PDF Viewer"},
                    {description: "", filename: "internal-nacl-plugin", length: 2, name: "Native Client"}
                ]
            });
            Object.defineProperty(navigator, 'languages', {get: () => ['zh-CN', 'zh', 'en-US', 'en']});
        """)
        try:
            await page.goto('https://www.tianyancha.com/search?key=网吧', wait_until='networkidle', timeout=20000)
            await page.wait_for_timeout(5000)
            current_url = page.url
            content = await page.content()
            if '/login' in current_url:
                return False
            for indicator in ['搜索结果', '家公司', '/company/', '退出', '我的订单', '个人中心', 'user-name', 'header-user']:
                if indicator in content:
                    return True
            if 'result-list' in content or 'search-result' in content:
                return True
            return False
        finally:
            await page.close()
    except Exception as e:
        logger.error("检测登录状态失败 (user=%s): %s", user_id, e)
        return False


async def _qr_login_start_for_user_async(user_id):
    """为指定用户启动二维码登录"""
    import base64
    from playwright.async_api import async_playwright

    global _login_sessions

    # 清理旧会话
    if user_id in _login_sessions:
        try:
            await _qr_login_cleanup_for_user_async(user_id)
        except Exception:
            pass

    data_dir = _get_user_data_dir(user_id)
    pw = await async_playwright().start()
    context = None

    try:
        # 关闭该用户的现有 context（释放 user_data_dir 锁）
        info = _user_contexts.pop(user_id, None)
        if info:
            try:
                await info['context'].close()
            except Exception:
                pass
            try:
                await info['playwright'].stop()
            except Exception:
                pass

        launch_args = [
            '--disable-blink-features=AutomationControlled',
            '--no-sandbox',
            '--disable-dev-shm-usage',
        ]

        import glob
        if sys.platform == 'win32':
            candidates = glob.glob(r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe') + \
                         glob.glob(r'C:\Program Files\Microsoft\Edge\Application\msedge.exe') + \
                         glob.glob(r'C:\Program Files\Google\Chrome\Application\chrome.exe') + \
                         glob.glob(r'C:\Program Files (x86)\Google\Chrome\Application\chrome.exe')
        else:
            candidates = glob.glob('/usr/bin/microsoft-edge*') + \
                         glob.glob('/opt/microsoft/msedge/msedge') + \
                         glob.glob('/usr/bin/google-chrome*') + \
                         glob.glob('/usr/bin/chromium-browser') + \
                         glob.glob('/snap/bin/chromium') + \
                         glob.glob('/usr/bin/chromium')

        for exe_path in candidates:
            try:
                context = await pw.chromium.launch_persistent_context(
                    user_data_dir=data_dir,
                    executable_path=exe_path,
                    headless=True,
                    viewport={'width': 1920, 'height': 1080},
                    locale='zh-CN',
                    timezone_id='Asia/Shanghai',
                    user_agent='Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
                    args=launch_args,
                    ignore_default_args=['--enable-automation'],
                )
                break
            except Exception:
                continue

        if context is None:
            context = await pw.chromium.launch_persistent_context(
                user_data_dir=data_dir,
                headless=True,
                viewport={'width': 1920, 'height': 1080},
                locale='zh-CN',
                timezone_id='Asia/Shanghai',
                user_agent='Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
                args=launch_args,
                ignore_default_args=['--enable-automation'],
            )

        page = await context.new_page()
        await page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            delete navigator.__proto__.webdriver;
            window.chrome = { runtime: {}, loadTimes: function(){}, csi: function(){}, app: {} };
            Object.defineProperty(navigator, 'plugins', {
                get: () => [
                    {description: "Portable Document Format", filename: "internal-pdf-viewer", length: 1, name: "Chrome PDF Plugin"},
                    {description: "", filename: "mhjfbmdgcfjbbpaeojofohoefgiehjai", length: 1, name: "Chrome PDF Viewer"},
                    {description: "", filename: "internal-nacl-plugin", length: 2, name: "Native Client"}
                ]
            });
            Object.defineProperty(navigator, 'languages', {get: () => ['zh-CN', 'zh', 'en-US', 'en']});
        """)

        await page.goto('https://www.tianyancha.com/login', wait_until='networkidle')
        await page.wait_for_timeout(5000)

        # 天眼查二维码是 canvas 渲染的
        qr_selectors = ['.qrcode-wrapper', 'canvas[width="180"]']
        qr_element = None
        for sel in qr_selectors:
            try:
                el = page.locator(sel).first
                if await el.is_visible(timeout=3000):
                    qr_element = el
                    break
            except Exception:
                continue

        if qr_element:
            screenshot_bytes = await qr_element.screenshot()
        else:
            screenshot_bytes = await page.screenshot()

        qr_base64 = base64.b64encode(screenshot_bytes).decode('utf-8')
        _login_sessions[user_id] = {
            'page': page,
            'context': context,
            'playwright': pw,
            'started_at': __import__('time').time(),
        }
        return {'qr_image': qr_base64}

    except Exception as e:
        logger.error("启动二维码登录失败 (user=%s): %s", user_id, e)
        try:
            if context:
                await context.close()
            await pw.stop()
        except Exception:
            pass
        return {'error': str(e)}


async def _qr_login_poll_for_user_async(user_id):
    """为指定用户轮询二维码登录状态"""
    import time as _time

    global _login_sessions, _user_contexts

    if user_id not in _login_sessions:
        return {'status': 'error', 'message': '无活跃的登录会话'}

    session = _login_sessions[user_id]
    page = session['page']
    context = session['context']
    pw = session['playwright']
    started_at = session['started_at']

    try:
        elapsed = _time.time() - started_at
        if elapsed > 300:
            await _qr_login_cleanup_for_user_async(user_id)
            return {'status': 'timeout'}

        current_url = page.url
        if '/login' not in current_url and 'tianyancha.com' in current_url:
            logger.info("二维码登录成功 (user=%s)", user_id)
            await _finalize_user_login(user_id, context, pw)
            return {'status': 'success'}

        content = await page.content()
        if '退出' in content or '我的订单' in content or '个人中心' in content:
            logger.info("二维码登录成功 (user=%s)", user_id)
            await _finalize_user_login(user_id, context, pw)
            return {'status': 'success'}

        # 检查二维码过期，尝试刷新
        refreshed_qr = None
        import base64
        try:
            refresh_selectors = ['.refresh-btn', '.qrcode-refresh', '[class*="refresh"]', 'text=点击刷新', 'text=刷新']
            for sel in refresh_selectors:
                try:
                    btn = page.locator(sel).first
                    if await btn.is_visible(timeout=500):
                        await btn.click()
                        await page.wait_for_timeout(2000)
                        qr_selectors = ['.qrcode-wrapper', 'canvas[width="180"]']
                        for qs in qr_selectors:
                            try:
                                el = page.locator(qs).first
                                if await el.is_visible(timeout=1000):
                                    ss = await el.screenshot()
                                    refreshed_qr = base64.b64encode(ss).decode('utf-8')
                                    break
                            except Exception:
                                continue
                        if refreshed_qr:
                            break
                except Exception:
                    continue
        except Exception:
            pass

        result = {'status': 'waiting'}
        if refreshed_qr:
            result['qr_image'] = refreshed_qr
            _login_sessions[user_id]['started_at'] = _time.time()
        return result

    except Exception as e:
        logger.error("轮询登录状态失败 (user=%s): %s", user_id, e)
        await _qr_login_cleanup_for_user_async(user_id)
        return {'status': 'error', 'error': str(e)}


async def _finalize_user_login(user_id, context, pw):
    """用户登录成功后：关闭 context，重置状态"""
    global _login_sessions, _user_contexts

    try:
        await context.close()
    except Exception:
        pass
    try:
        await pw.stop()
    except Exception:
        pass

    _login_sessions.pop(user_id, None)
    _user_contexts.pop(user_id, None)


async def _qr_login_cleanup_for_user_async(user_id):
    """清理指定用户的二维码登录会话"""
    global _login_sessions, _user_contexts

    session = _login_sessions.pop(user_id, None)
    if session:
        try:
            await session['context'].close()
        except Exception:
            pass
        try:
            await session['playwright'].stop()
        except Exception:
            pass

    _user_contexts.pop(user_id, None)


async def _get_page_content_async(url, timeout=30000):
    """
    导航到 URL 并返回页面 HTML 内容

    Args:
        url: 目标 URL
        timeout: 超时时间（毫秒）

    Returns:
        str: 页面 HTML 内容，失败返回 None
    """
    context = await _init_async()

    page = await context.new_page()

    try:
        logger.info("导航到: %s", url)
        await page.goto(url, wait_until='domcontentloaded', timeout=timeout)

        # 等待页面完全加载（给 JS 渲染时间）
        await page.wait_for_timeout(3000)

        # 获取页面 HTML
        content = await page.content()
        logger.info("页面加载完成: %s (%d bytes)", url, len(content))
        return content

    except Exception as e:
        logger.error("页面加载失败: %s - %s", url, e)
        return None
    finally:
        await page.close()


async def _screenshot_async(path):
    """
    对当前页面截图

    Args:
        path: 截图保存路径

    Returns:
        bool: 是否成功
    """
    context = await _init_async()

    pages = context.pages
    if not pages:
        logger.warning("没有打开的页面，无法截图")
        return False

    try:
        page = pages[-1]
        await page.screenshot(path=path, full_page=False)
        logger.info("截图已保存: %s", path)
        return True
    except Exception as e:
        logger.error("截图失败: %s", e)
        return False


async def _login_interactive_async():
    """
    打开可见浏览器窗口让用户扫码登录天眼查

    使用与 headless 相同的持久化上下文（user_data_dir），
    登录成功后 cookies 自动保存，headless 模式可以直接复用。

    Returns:
        bool: 是否登录成功
    """
    from playwright.async_api import async_playwright

    data_dir = _get_data_dir()
    pw = await async_playwright().start()
    context = None
    login_success = False

    try:
        # 查找系统浏览器
        import glob
        if sys.platform == 'win32':
            edge_paths = glob.glob(r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe') + \
                         glob.glob(r'C:\Program Files\Microsoft\Edge\Application\msedge.exe')
            chrome_paths = glob.glob(r'C:\Program Files\Google\Chrome\Application\chrome.exe') + \
                           glob.glob(r'C:\Program Files (x86)\Google\Chrome\Application\chrome.exe')
        else:
            edge_paths = glob.glob('/usr/bin/microsoft-edge*') + \
                         glob.glob('/opt/microsoft/msedge/msedge')
            chrome_paths = glob.glob('/usr/bin/google-chrome*') + \
                           glob.glob('/usr/bin/chromium-browser') + \
                           glob.glob('/snap/bin/chromium') + \
                           glob.glob('/usr/bin/chromium')

        # 优先使用系统浏览器
        for exe_path in edge_paths + chrome_paths:
            try:
                context = await pw.chromium.launch_persistent_context(
                    user_data_dir=data_dir,
                    executable_path=exe_path,
                    headless=False,
                    viewport={'width': 1280, 'height': 800},
                    locale='zh-CN',
                    timezone_id='Asia/Shanghai',
                    args=[
                        '--disable-blink-features=AutomationControlled',
                        '--no-sandbox',
                    ]
                )
                logger.info("使用系统浏览器登录: %s", exe_path)
                break
            except Exception:
                continue

        # 如果系统浏览器不可用，使用 Playwright 内置
        if context is None:
            context = await pw.chromium.launch_persistent_context(
                user_data_dir=data_dir,
                headless=False,
                viewport={'width': 1280, 'height': 800},
                locale='zh-CN',
                timezone_id='Asia/Shanghai',
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--no-sandbox',
                ]
            )

        page = await context.new_page()

        # 导航到天眼查登录页
        await page.goto('https://www.tianyancha.com/login', wait_until='domcontentloaded')

        logger.info("请在浏览器中扫码登录天眼查...")
        print("请在弹出的浏览器窗口中扫码登录天眼查...")
        print("登录成功后，程序将自动继续。")

        # 等待用户登录完成，最多等待 5 分钟
        timeout = 300
        check_interval = 2
        elapsed = 0

        while elapsed < timeout:
            await asyncio.sleep(check_interval)
            elapsed += check_interval

            try:
                current_url = page.url

                # 检查是否已经不在登录页（登录成功会跳转）
                if '/login' not in current_url and 'tianyancha.com' in current_url:
                    logger.info("检测到登录成功（URL跳转），当前URL: %s", current_url)
                    login_success = True
                    break

                # 检查页面内容是否有登录成功的标志
                content = await page.content()
                if '退出' in content or '我的订单' in content or '个人中心' in content:
                    logger.info("检测到登录成功（页面内容）")
                    login_success = True
                    break

            except Exception as e:
                # 浏览器可能已关闭
                logger.debug("检测登录状态时出错: %s", e)
                break

        # 关闭浏览器（cookies 已自动保存到 user_data_dir）
        try:
            await context.close()
        except Exception:
            pass
        await pw.stop()

        return login_success

    except Exception as e:
        logger.error("登录过程失败: %s", e)
        try:
            if context:
                await context.close()
            await pw.stop()
        except Exception:
            pass
        return False


async def _qr_login_start_async():
    """
    启动二维码登录会话：用无头浏览器打开天眼查登录页，截取二维码图片返回

    Returns:
        dict: {'qr_image': base64_str} 或 {'error': msg}
    """
    import base64
    from playwright.async_api import async_playwright

    global _context, _playwright, _login_session

    # 清理旧会话
    if _login_session:
        try:
            await _qr_login_cleanup_async()
        except Exception:
            pass

    data_dir = _get_data_dir()
    pw = await async_playwright().start()
    context = None

    try:
        # 关闭全局 headless context（释放 user_data_dir 锁）
        if _context is not None:
            try:
                await _context.close()
            except Exception:
                pass
            _context = None

        # 查找系统浏览器
        import glob
        exe_path = None
        if sys.platform == 'win32':
            candidates = glob.glob(r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe') + \
                         glob.glob(r'C:\Program Files\Microsoft\Edge\Application\msedge.exe') + \
                         glob.glob(r'C:\Program Files\Google\Chrome\Application\chrome.exe') + \
                         glob.glob(r'C:\Program Files (x86)\Google\Chrome\Application\chrome.exe')
        else:
            candidates = glob.glob('/usr/bin/microsoft-edge*') + \
                         glob.glob('/opt/microsoft/msedge/msedge') + \
                         glob.glob('/usr/bin/google-chrome*') + \
                         glob.glob('/usr/bin/chromium-browser') + \
                         glob.glob('/snap/bin/chromium') + \
                         glob.glob('/usr/bin/chromium')

        launch_args = [
            '--disable-blink-features=AutomationControlled',
            '--no-sandbox',
            '--disable-dev-shm-usage',
        ]

        # 查找系统浏览器
        import glob
        if sys.platform == 'win32':
            candidates = glob.glob(r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe') + \
                         glob.glob(r'C:\Program Files\Microsoft\Edge\Application\msedge.exe') + \
                         glob.glob(r'C:\Program Files\Google\Chrome\Application\chrome.exe') + \
                         glob.glob(r'C:\Program Files (x86)\Google\Chrome\Application\chrome.exe')
        else:
            candidates = glob.glob('/usr/bin/microsoft-edge*') + \
                         glob.glob('/opt/microsoft/msedge/msedge') + \
                         glob.glob('/usr/bin/google-chrome*') + \
                         glob.glob('/usr/bin/chromium-browser') + \
                         glob.glob('/snap/bin/chromium') + \
                         glob.glob('/usr/bin/chromium')

        for exe_path in candidates:
            try:
                context = await pw.chromium.launch_persistent_context(
                    user_data_dir=data_dir,
                    executable_path=exe_path,
                    headless=True,
                    viewport={'width': 1920, 'height': 1080},
                    locale='zh-CN',
                    timezone_id='Asia/Shanghai',
                    user_agent='Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
                    args=launch_args,
                    ignore_default_args=['--enable-automation'],
                )
                logger.info("二维码登录使用浏览器: %s", exe_path)
                break
            except Exception:
                continue

        if context is None:
            context = await pw.chromium.launch_persistent_context(
                user_data_dir=data_dir,
                headless=True,
                viewport={'width': 1920, 'height': 1080},
                locale='zh-CN',
                timezone_id='Asia/Shanghai',
                user_agent='Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
                args=launch_args,
                ignore_default_args=['--enable-automation'],
            )

        page = await context.new_page()

        # 反检测脚本
        await page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            delete navigator.__proto__.webdriver;
            window.chrome = { runtime: {}, loadTimes: function(){}, csi: function(){}, app: {} };
            Object.defineProperty(navigator, 'plugins', {
                get: () => [
                    {description: "Portable Document Format", filename: "internal-pdf-viewer", length: 1, name: "Chrome PDF Plugin"},
                    {description: "", filename: "mhjfbmdgcfjbbpaeojofohoefgiehjai", length: 1, name: "Chrome PDF Viewer"},
                    {description: "", filename: "internal-nacl-plugin", length: 2, name: "Native Client"}
                ]
            });
            Object.defineProperty(navigator, 'languages', {get: () => ['zh-CN', 'zh', 'en-US', 'en']});
        """)

        await page.goto('https://www.tianyancha.com/login', wait_until='networkidle')
        await page.wait_for_timeout(5000)

        # 天眼查二维码是 canvas 渲染的，选择器按优先级尝试
        qr_selectors = [
            '.qrcode-wrapper',
            '.login-scan .qrcode-wrapper',
            'canvas[width="180"]',
        ]
        qr_element = None
        for sel in qr_selectors:
            try:
                el = page.locator(sel).first
                if await el.is_visible(timeout=3000):
                    qr_element = el
                    logger.info("找到二维码元素: %s", sel)
                    break
            except Exception:
                continue

        if qr_element:
            screenshot_bytes = await qr_element.screenshot()
        else:
            # 兜底：截取整个页面
            logger.warning("未找到二维码元素，使用整页截图")
            screenshot_bytes = await page.screenshot()

        qr_base64 = base64.b64encode(screenshot_bytes).decode('utf-8')

        _login_session = {
            'page': page,
            'context': context,
            'playwright': pw,
            'started_at': __import__('time').time(),
        }

        logger.info("二维码登录会话已启动")
        return {'qr_image': qr_base64}

    except Exception as e:
        logger.error("启动二维码登录失败: %s", e)
        try:
            if context:
                await context.close()
            await pw.stop()
        except Exception:
            pass
        return {'error': str(e)}


async def _qr_login_poll_async():
    """
    轮询二维码登录状态

    Returns:
        dict: {'status': 'waiting'|'success'|'timeout'|'error', 'qr_image': ...}
    """
    import base64
    import time as _time

    global _login_session, _context

    if not _login_session:
        return {'status': 'error', 'message': '无活跃的登录会话'}

    page = _login_session['page']
    context = _login_session['context']
    pw = _login_session['playwright']
    started_at = _login_session['started_at']

    try:
        elapsed = _time.time() - started_at
        if elapsed > 300:  # 5 分钟超时
            await _qr_login_cleanup_async()
            return {'status': 'timeout'}

        # 检查登录成功
        current_url = page.url
        if '/login' not in current_url and 'tianyancha.com' in current_url:
            logger.info("二维码登录成功（URL 跳转）")
            await _finalize_login(context, pw)
            return {'status': 'success'}

        content = await page.content()
        if '退出' in content or '我的订单' in content or '个人中心' in content:
            logger.info("二维码登录成功（页面内容）")
            await _finalize_login(context, pw)
            return {'status': 'success'}

        # 检查二维码是否过期，尝试刷新
        refreshed_qr = None
        try:
            # 查找刷新按钮
            refresh_selectors = [
                '.refresh-btn',
                '.qrcode-refresh',
                '[class*="refresh"]',
                'text=点击刷新',
                'text=刷新',
            ]
            for sel in refresh_selectors:
                try:
                    btn = page.locator(sel).first
                    if await btn.is_visible(timeout=500):
                        await btn.click()
                        await page.wait_for_timeout(2000)
                        # 重新截取二维码
                        qr_selectors = [
                            '.qrcode-wrapper',
                            'canvas[width="180"]',
                        ]
                        for qs in qr_selectors:
                            try:
                                el = page.locator(qs).first
                                if await el.is_visible(timeout=1000):
                                    ss = await el.screenshot()
                                    refreshed_qr = base64.b64encode(ss).decode('utf-8')
                                    break
                            except Exception:
                                continue
                        if refreshed_qr:
                            break
                except Exception:
                    continue
        except Exception:
            pass

        result = {'status': 'waiting'}
        if refreshed_qr:
            result['qr_image'] = refreshed_qr
            _login_session['started_at'] = _time.time()  # 重置过期计时
        return result

    except Exception as e:
        logger.error("轮询登录状态失败: %s", e)
        await _qr_login_cleanup_async()
        return {'status': 'error', 'error': str(e)}


async def _finalize_login(context, pw):
    """登录成功后：关闭登录 context，重置全局状态以便重新初始化"""
    global _login_session, _context, _playwright

    try:
        await context.close()
    except Exception:
        pass
    try:
        await pw.stop()
    except Exception:
        pass

    _login_session = None
    _context = None
    _playwright = None


async def _qr_login_cleanup_async():
    """清理二维码登录会话"""
    global _login_session, _context, _playwright

    if not _login_session:
        return

    session = _login_session
    _login_session = None

    try:
        await session['context'].close()
    except Exception:
        pass
    try:
        await session['playwright'].stop()
    except Exception:
        pass

    # 重置全局状态
    _context = None
    _playwright = None
    logger.info("二维码登录会话已清理")


async def _is_logged_in_async():
    """
    检测当前 session 是否已登录天眼查

    Returns:
        bool: 是否已登录
    """
    try:
        context = await _init_async()
        page = await context.new_page()

        # 反检测脚本
        await page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            delete navigator.__proto__.webdriver;
            window.chrome = { runtime: {}, loadTimes: function(){}, csi: function(){}, app: {} };
            Object.defineProperty(navigator, 'plugins', {
                get: () => [
                    {description: "Portable Document Format", filename: "internal-pdf-viewer", length: 1, name: "Chrome PDF Plugin"},
                    {description: "", filename: "mhjfbmdgcfjbbpaeojofohoefgiehjai", length: 1, name: "Chrome PDF Viewer"},
                    {description: "", filename: "internal-nacl-plugin", length: 2, name: "Native Client"}
                ]
            });
            Object.defineProperty(navigator, 'languages', {get: () => ['zh-CN', 'zh', 'en-US', 'en']});
        """)

        try:
            # 访问天眼查搜索页（需要登录才能看到结果）
            await page.goto('https://www.tianyancha.com/search?key=网吧', wait_until='domcontentloaded', timeout=20000)
            await page.wait_for_timeout(3000)

            current_url = page.url
            content = await page.content()

            # 检查是否被重定向到登录页
            if '/login' in current_url:
                logger.info("被重定向到登录页，未登录")
                return False

            # 检查页面是否包含搜索结果（多种可能的标志）
            login_indicators = [
                '搜索结果',
                '家公司',
                '/company/',
                '退出',           # 已登录时显示"退出"按钮
                '我的订单',       # 已登录时显示的菜单
                '个人中心',       # 已登录时显示的菜单
                'user-name',      # 用户名元素
                'header-user',    # 用户头像区域
            ]

            for indicator in login_indicators:
                if indicator in content:
                    logger.info("检测到登录状态标志: %s", indicator)
                    return True

            # 检查是否有搜索结果列表
            if 'result-list' in content or 'search-result' in content:
                logger.info("检测到搜索结果列表")
                return True

            return False
        finally:
            await page.close()
    except Exception as e:
        logger.error("登录状态检测失败: %s", e)
        return False


# ==================== 同步接口 ====================

def init_browser():
    """初始化浏览器"""
    _run_async(_init_async())


def close_browser():
    """关闭浏览器"""
    _run_async(_close_async())


def get_page_content(url, timeout=30000):
    """
    导航到 URL 并返回页面 HTML

    Args:
        url: 目标 URL
        timeout: 超时时间（毫秒）

    Returns:
        str: 页面 HTML，失败返回 None
    """
    return _run_async(_get_page_content_async(url, timeout))


def screenshot(path):
    """
    截图

    Args:
        path: 截图保存路径

    Returns:
        bool: 是否成功
    """
    return _run_async(_screenshot_async(path))


def login_interactive():
    """
    打开可见浏览器让用户扫码登录

    Returns:
        bool: 是否登录成功
    """
    return _run_async(_login_interactive_async())


def is_logged_in():
    """
    检测是否已登录

    Returns:
        bool: 是否已登录
    """
    return _login_submit(_is_logged_in_async())


def qr_login_start():
    """启动二维码登录会话，返回二维码图片 base64"""
    return _login_submit(_qr_login_start_async())


def qr_login_poll():
    """轮询二维码登录状态"""
    return _login_submit(_qr_login_poll_async())


def qr_login_cleanup():
    """清理二维码登录会话"""
    return _login_submit(_qr_login_cleanup_async())


# ==================== 按用户隔离的同步接口 ====================

def get_page_content_for_user(user_id, url, timeout=30000):
    """为指定用户获取页面内容"""
    return _login_submit(_get_page_content_for_user_async(user_id, url, timeout))


def is_logged_in_for_user(user_id):
    """为指定用户检测天眼查登录状态"""
    return _login_submit(_is_logged_in_for_user_async(user_id))


def qr_login_start_for_user(user_id):
    """为指定用户启动二维码登录"""
    return _login_submit(_qr_login_start_for_user_async(user_id))


def qr_login_poll_for_user(user_id):
    """为指定用户轮询二维码登录状态"""
    return _login_submit(_qr_login_poll_for_user_async(user_id))


def qr_login_cleanup_for_user(user_id):
    """为指定用户清理二维码登录会话"""
    return _login_submit(_qr_login_cleanup_for_user_async(user_id))

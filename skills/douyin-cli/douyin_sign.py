"""
抖音 Web 签名与浏览器管理模块
通过 Playwright 浏览器维护登录态，拦截 API 响应获取数据。
"""

import atexit
import json
import time
from pathlib import Path
from urllib.parse import quote, unquote

_playwright = None
_browser = None
_context = None
_page = None

SKILL_DIR = Path(__file__).parent
COOKIE_FILE = SKILL_DIR / "data" / "douyin_cookie.txt"

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)


def _p(msg: str):
    print(msg, flush=True)


def _parse_cookie_string(cookie_str: str) -> list[dict]:
    cookies = []
    for part in cookie_str.split(";"):
        part = part.strip()
        if "=" in part:
            name, value = part.split("=", 1)
            cookies.append({
                "name": name.strip(),
                "value": value.strip(),
                "domain": ".douyin.com",
                "path": "/",
            })
    return cookies


def _has_valid_cookie() -> bool:
    if not COOKIE_FILE.exists():
        return False
    cookie_str = COOKIE_FILE.read_text().strip()
    return bool(cookie_str) and "ttwid" in cookie_str


def _ensure_browser():
    """懒加载：有 Cookie 用 headless，没有则提示登录"""
    global _playwright, _browser, _context, _page

    if _page is not None:
        return

    if not _has_valid_cookie():
        raise RuntimeError(
            "未登录抖音。请先执行以下任一方式登录:\n"
            "  1. 扫码登录: python douyin_sign.py login\n"
            "  2. 手动粘贴: python douyin_sign.py set-cookie \"你的cookie字符串\""
        )

    from playwright.sync_api import sync_playwright
    from playwright_stealth import Stealth

    _playwright = sync_playwright().start()
    # 抖音反爬较强，用非 headless 模式以便用户手动过验证码
    _browser = _playwright.chromium.launch(headless=False)
    _context = _browser.new_context(
        user_agent=UA,
        viewport={"width": 1440, "height": 900},
        locale="zh-CN",
        timezone_id="Asia/Shanghai",
    )

    cookie_str = COOKIE_FILE.read_text().strip()
    _context.add_cookies(_parse_cookie_string(cookie_str))

    _page = _context.new_page()
    Stealth().apply_stealth_sync(_page)

    _page.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
        Object.defineProperty(navigator, 'languages', {get: () => ['zh-CN', 'zh', 'en']});
    """)

    for attempt in range(3):
        try:
            _page.goto("https://www.douyin.com", wait_until="domcontentloaded", timeout=15000)
            break
        except Exception:
            if attempt < 2:
                time.sleep(2)
    time.sleep(3)

    atexit.register(_shutdown)


def _shutdown():
    global _playwright, _browser, _context, _page
    try:
        if _browser:
            _browser.close()
        if _playwright:
            _playwright.stop()
    except Exception:
        pass
    _browser = _page = _context = _playwright = None


# ── API 拦截 ─────────────────────────────────────

def _check_and_wait_captcha(max_wait: int = 180) -> None:
    """检测验证码/安全验证，等待用户手动完成（含图形验证+短信验证，最长 3 分钟）。"""
    try:
        # 检测标志：#captcha_container、验证码 iframe、或手机号输入框
        captcha = _page.locator('#captcha_container')
        verify_iframe = _page.locator('iframe[src*="verifycenter"], iframe[src*="captcha"]')
        phone_input = _page.locator('input[placeholder*="手机"], input[type="tel"]')

        has_verify = False
        if captcha.count() > 0 and captcha.first.is_visible():
            has_verify = True
        elif verify_iframe.count() > 0 and verify_iframe.first.is_visible():
            has_verify = True
        elif phone_input.count() > 0 and phone_input.first.is_visible():
            has_verify = True

        if not has_verify:
            return

        _p("检测到安全验证（可能含图形验证+短信验证），请在浏览器中完成...")
        _p("完成后页面会自动跳转，脚本会自动检测。")

        for i in range(max_wait // 2):
            time.sleep(2)
            try:
                # 所有验证元素都消失 = 通过
                cap_vis = captcha.count() > 0 and captcha.first.is_visible()
                iframe_vis = verify_iframe.count() > 0 and verify_iframe.first.is_visible()
                phone_vis = phone_input.count() > 0 and phone_input.first.is_visible()
                if not cap_vis and not iframe_vis and not phone_vis:
                    _p("安全验证已通过")
                    time.sleep(3)
                    return
            except Exception:
                _p("安全验证已通过")
                time.sleep(3)
                return
            if i % 10 == 9:
                _p(f"  等待验证... ({(i+1)*2}秒)")
        _p("验证等待超时（3 分钟）")
    except Exception:
        pass


def capture_api_response(url: str, api_pattern: str, timeout: int = 20) -> dict | None:
    """导航到 URL，拦截匹配 api_pattern 的 API 响应并返回 JSON。"""
    _ensure_browser()

    captured = []

    def _on_response(response):
        if api_pattern in response.url and response.status == 200:
            try:
                captured.append(response.json())
            except Exception:
                pass

    _page.on("response", _on_response)
    try:
        _page.goto(url, wait_until="domcontentloaded", timeout=timeout * 1000)
        # 等待：要么捕获到 API 响应，要么等待用户过验证码（最多 3 分钟）
        for i in range(90):
            time.sleep(2)
            if captured:
                break
            if i % 10 == 9:
                _p(f"  等待页面加载... ({(i+1)*2}秒)")
                # 如果有验证码提示一下
                cap = _page.locator('#captcha_container')
                iframe = _page.locator('iframe[src*="verifycenter"]')
                try:
                    if (cap.count() > 0 and cap.first.is_visible()) or \
                       (iframe.count() > 0 and iframe.first.is_visible()):
                        _p("  请在浏览器中完成验证码...")
                except Exception:
                    pass
    except Exception:
        pass
    finally:
        _page.remove_listener("response", _on_response)

    return captured[0] if captured else None


def capture_multiple_api_responses(url: str, api_pattern: str,
                                    timeout: int = 20) -> list[dict]:
    """导航到 URL，拦截所有匹配 api_pattern 的 API 响应。"""
    _ensure_browser()

    captured = []

    def _on_response(response):
        if api_pattern in response.url and response.status == 200:
            try:
                captured.append(response.json())
            except Exception:
                pass

    _page.on("response", _on_response)
    try:
        _page.goto(url, wait_until="networkidle", timeout=timeout * 1000)
        time.sleep(3)
    except Exception:
        pass
    finally:
        _page.remove_listener("response", _on_response)

    return captured


# ── RENDER_DATA 提取 ─────────────────────────────

def extract_render_data(url: str, timeout: int = 20) -> dict | None:
    """导航到页面，提取 <script id="RENDER_DATA"> 中的 JSON 数据。"""
    _ensure_browser()

    try:
        _page.goto(url, wait_until="networkidle", timeout=timeout * 1000)
        time.sleep(2)
    except Exception:
        pass

    try:
        raw = _page.evaluate('''() => {
            const el = document.getElementById('RENDER_DATA');
            return el ? el.textContent : null;
        }''')
        if raw:
            decoded = unquote(raw)
            return json.loads(decoded)
    except Exception:
        pass

    return None


# ── 搜索 ────────────────────────────────────────

def search_videos(keyword: str, timeout: int = 25) -> dict:
    """搜索抖音视频。优先 API 拦截，fallback 到 RENDER_DATA。"""
    _ensure_browser()
    url = f"https://www.douyin.com/search/{quote(keyword)}?type=video"

    captured = []

    def _on_response(response):
        u = response.url
        if response.status == 200 and ("aweme" in u) and \
                ("/web/search/item/" in u or "/general/search/single/" in u):
            try:
                data = response.json()
                if data.get("aweme_list") or data.get("data"):
                    captured.append(data)
            except Exception:
                pass

    _page.on("response", _on_response)
    try:
        _page.goto(url, wait_until="domcontentloaded", timeout=timeout * 1000)
        # 等足够久让搜索 API 完成（含验证码时间）
        for i in range(90):
            time.sleep(2)
            if captured:
                _p(f"  API 响应已捕获")
                break
            if i % 10 == 9:
                _p(f"  等待数据加载... ({(i+1)*2}秒)")
                try:
                    cap = _page.locator('#captcha_container, iframe[src*="verifycenter"]')
                    if cap.count() > 0 and cap.first.is_visible():
                        _p("  请在浏览器中完成验证码...")
                except Exception:
                    pass
    except Exception:
        pass
    finally:
        _page.remove_listener("response", _on_response)

    if captured:
        return captured[0]

    # Fallback: 从 RENDER_DATA 提取
    try:
        raw = _page.evaluate('''() => {
            const el = document.getElementById('RENDER_DATA');
            return el ? el.textContent : null;
        }''')
        if raw:
            data = json.loads(unquote(raw))
            for key, val in data.items():
                if isinstance(val, dict):
                    aweme_list = val.get("aweme_list") or val.get("data")
                    if aweme_list and isinstance(aweme_list, list) and len(aweme_list) > 0:
                        return {"aweme_list": aweme_list, "status_code": 0}
    except Exception:
        pass

    return {"status_code": -1, "aweme_list": [], "msg": "未捕获到搜索响应"}


def search_users(keyword: str, timeout: int = 20) -> dict:
    """搜索抖音用户。"""
    url = f"https://www.douyin.com/search/{quote(keyword)}?type=user"
    result = capture_api_response(url, "/aweme/v1/web/discover/search/", timeout)
    if result is None:
        result = capture_api_response(url, "/aweme/v1/web/general/search/single/", timeout)
    if result:
        return result
    return {"status_code": -1, "data": [], "msg": "未捕获到搜索响应"}


# ── 视频详情 ─────────────────────────────────────

def get_video_detail(aweme_id: str, timeout: int = 20) -> dict:
    """获取视频详情，优先 API 拦截，fallback 到 RENDER_DATA。"""
    url = f"https://www.douyin.com/video/{aweme_id}"

    # 方式1: API 拦截
    result = capture_api_response(url, "/aweme/v1/web/aweme/detail/", timeout)
    if result and result.get("aweme_detail"):
        return result

    # 方式2: RENDER_DATA
    render = extract_render_data(url, timeout)
    if render:
        for key, val in render.items():
            if isinstance(val, dict):
                detail = val.get("aweme", {}).get("detail")
                if detail:
                    return {"aweme_detail": detail}

    return {"aweme_detail": None, "msg": "获取视频详情失败"}


# ── 评论 ─────────────────────────────────────────

def get_comments(aweme_id: str, timeout: int = 20) -> dict:
    """获取视频评论，通过 API 拦截。"""
    url = f"https://www.douyin.com/video/{aweme_id}"

    _ensure_browser()
    captured = []

    def _on_response(response):
        if "/aweme/v1/web/comment/list/" in response.url and response.status == 200:
            # 排除 reply 接口
            if "/reply/" not in response.url:
                try:
                    captured.append(response.json())
                except Exception:
                    pass

    _page.on("response", _on_response)
    try:
        _page.goto(url, wait_until="networkidle", timeout=timeout * 1000)
        time.sleep(3)
        # 滚动页面触发评论加载
        _page.evaluate("window.scrollTo(0, document.body.scrollHeight / 2)")
        time.sleep(2)
    except Exception:
        pass
    finally:
        _page.remove_listener("response", _on_response)

    if captured:
        return captured[0]
    return {"comments": [], "has_more": 0, "cursor": 0, "msg": "未捕获到评论"}


# ── 用户主页 ─────────────────────────────────────

def get_user_profile(sec_user_id: str, timeout: int = 20) -> dict:
    """获取用户主页信息，通过 API 拦截。"""
    url = f"https://www.douyin.com/user/{sec_user_id}"

    results = capture_multiple_api_responses(url, "/aweme/v1/web/user/profile/other/", timeout)
    if results:
        return results[0]

    # fallback: RENDER_DATA
    render = extract_render_data(url, timeout)
    if render:
        for key, val in render.items():
            if isinstance(val, dict) and "user" in val:
                return {"user": val["user"]}

    return {"user": None, "msg": "获取用户信息失败"}


def get_user_posts(sec_user_id: str, timeout: int = 20) -> dict:
    """获取用户发布的视频列表。"""
    url = f"https://www.douyin.com/user/{sec_user_id}"
    result = capture_api_response(url, "/aweme/v1/web/aweme/post/", timeout)
    if result:
        return result
    return {"aweme_list": [], "has_more": 0, "msg": "未捕获到用户作品"}


# ── 登录 ─────────────────────────────────────────

def login_interactive(timeout: int = 120):
    """打开浏览器让用户扫码登录抖音。"""
    global _playwright, _browser, _context, _page

    _shutdown()

    from playwright.sync_api import sync_playwright
    from playwright_stealth import Stealth

    _playwright = sync_playwright().start()
    _browser = _playwright.chromium.launch(headless=False)
    _context = _browser.new_context(user_agent=UA)
    _page = _context.new_page()
    Stealth().apply_stealth_sync(_page)

    _page.goto("https://www.douyin.com", wait_until="domcontentloaded")

    _p(f"浏览器已打开，请扫码登录抖音（{timeout} 秒内完成）。")
    _p("登录成功后页面会自动跳转，脚本会自动检测并保存 Cookie。")

    done = False
    for i in range(timeout // 2):
        time.sleep(2)
        try:
            cookies = {c["name"]: c["value"] for c in _context.cookies()}
            # 登录成功标志：有 sessionid 或 LOGIN_STATUS=1
            has_session = "sessionid" in cookies or "sessionid_ss" in cookies
            login_status = cookies.get("LOGIN_STATUS") == "1"
            if has_session or login_status:
                time.sleep(3)
                done = True
                _p("检测到登录成功，正在保存 Cookie...")
                break
        except Exception:
            pass
        if i % 10 == 9:
            _p(f"  仍在等待扫码... ({(i + 1) * 2}秒)")

    if not done:
        _p("等待超时。关闭浏览器。")
        _browser.close()
        _playwright.stop()
        _browser = _page = _context = _playwright = None
        return

    # 保存 cookie
    cookie_pairs = {}
    for c in _context.cookies():
        cookie_pairs[c["name"]] = c["value"]
    cookie_str = "; ".join(f"{k}={v}" for k, v in cookie_pairs.items())

    COOKIE_FILE.parent.mkdir(parents=True, exist_ok=True)
    COOKIE_FILE.write_text(cookie_str)
    _p(f"Cookie 已保存到 {COOKIE_FILE}")

    _browser.close()
    _browser = _page = _context = None
    _playwright.stop()
    _playwright = None


def save_cookie_string(cookie_str: str) -> None:
    """手动保存 Cookie 字符串。"""
    cookie_str = cookie_str.strip()
    if not cookie_str:
        _p("Cookie 不能为空")
        return
    COOKIE_FILE.parent.mkdir(parents=True, exist_ok=True)
    COOKIE_FILE.write_text(cookie_str)
    cookies = _parse_cookie_string(cookie_str)
    names = {c["name"] for c in cookies}
    _p(f"Cookie 已保存（{len(cookies)} 项）")
    if "ttwid" not in names:
        _p("警告: 缺少 ttwid，可能无法正常使用")


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "login":
        login_interactive()
    elif len(sys.argv) > 2 and sys.argv[1] == "set-cookie":
        save_cookie_string(sys.argv[2])
    elif len(sys.argv) > 1 and sys.argv[1] == "status":
        if _has_valid_cookie():
            cookies = _parse_cookie_string(COOKIE_FILE.read_text().strip())
            names = {c["name"] for c in cookies}
            logged_in = "sessionid" in names or "sessionid_ss" in names
            print(f"{'已登录' if logged_in else '有 Cookie 但未登录'}（{len(cookies)} 个 cookie）")
        else:
            print("未登录")
    else:
        print("用法:")
        print("  python douyin_sign.py login              # 扫码登录")
        print('  python douyin_sign.py set-cookie "..."    # 手动粘贴 Cookie')
        print("  python douyin_sign.py status             # 检查登录状态")

"""
小红书创作者中心 · 发布图文笔记（全自动版）

通过 Playwright 自动化 creator.xiaohongshu.com 的发布流程。
支持 headless 运行，截图确认后一键发布。

用法:
  python xhs_publish.py login                      # 扫码登录创作者中心
  python xhs_publish.py publish --draft draft.md --images img1.jpg img2.jpg
  python xhs_publish.py publish --draft draft.md --images img1.jpg --auto  # 跳过确认直接发
"""

import argparse
import json
import sys
import time
from pathlib import Path

SKILL_DIR = Path(__file__).parent
COOKIE_FILE = SKILL_DIR / "data" / "creator_cookie.txt"
SIGNAL_FILE = SKILL_DIR / "data" / ".creator_login_done"
SCREENSHOT_DIR = SKILL_DIR / "data" / "screenshots"

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
                "domain": ".xiaohongshu.com",
                "path": "/",
            })
    return cookies


def _save_cookies(context) -> str:
    seen = {}
    for c in context.cookies():
        seen[c["name"]] = c["value"]
    cookie_str = "; ".join(f"{k}={v}" for k, v in seen.items())
    COOKIE_FILE.parent.mkdir(parents=True, exist_ok=True)
    COOKIE_FILE.write_text(cookie_str)
    return cookie_str


def _screenshot(page, name: str) -> str:
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    path = SCREENSHOT_DIR / f"publish_{name}.png"
    page.screenshot(path=str(path), full_page=False)
    _p(f"  [截图] {path}")
    return str(path)


def login(timeout: int = 120):
    """打开可见浏览器让用户扫码登录创作者中心"""
    from playwright.sync_api import sync_playwright
    from playwright_stealth import Stealth

    pw = sync_playwright().start()
    browser = pw.chromium.launch(headless=False)
    context = browser.new_context(user_agent=UA)
    if COOKIE_FILE.exists():
        cookie_str = COOKIE_FILE.read_text().strip()
        if cookie_str:
            context.add_cookies(_parse_cookie_string(cookie_str))
    page = context.new_page()
    Stealth().apply_stealth_sync(page)

    page.goto("https://creator.xiaohongshu.com", wait_until="domcontentloaded")
    SIGNAL_FILE.unlink(missing_ok=True)

    _p(f"浏览器已打开，请扫码登录小红书创作者中心（{timeout} 秒内完成）。")
    _p(f"登录成功后，运行: touch {SIGNAL_FILE}")
    _p("正在等待登录信号...")

    done = False
    for i in range(timeout // 2):
        time.sleep(2)
        if SIGNAL_FILE.exists():
            SIGNAL_FILE.unlink(missing_ok=True)
            done = True
            _p("收到登录信号，正在保存 Cookie...")
            break
        if i % 10 == 9:
            _p(f"  仍在等待... ({(i + 1) * 2}秒)")

    if not done:
        _p("等待超时，关闭浏览器。")
        browser.close()
        pw.stop()
        return False

    _save_cookies(context)
    _p(f"Creator Cookie 已保存到 {COOKIE_FILE}")
    browser.close()
    pw.stop()
    return True


def _parse_draft(draft_path: str) -> dict:
    """从 Markdown 草稿文件解析标题、正文、标签"""
    text = Path(draft_path).read_text(encoding="utf-8")
    result = {"title": "", "content": "", "tags": []}
    lines = text.split("\n")
    in_section = None
    content_lines = []

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("## 标题"):
            in_section = "title"
            continue
        elif stripped.startswith("## 正文"):
            in_section = "content"
            continue
        elif stripped.startswith("## 话题标签"):
            in_section = "tags"
            continue
        elif stripped.startswith("## "):
            in_section = None
            continue
        elif stripped.startswith("# "):
            in_section = None
            continue
        elif stripped.startswith("---"):
            continue

        if in_section == "title" and stripped:
            result["title"] = stripped
        elif in_section == "content":
            if stripped.startswith(">"):
                content_lines.append(stripped.lstrip("> ").strip())
            elif stripped:
                content_lines.append(stripped)
            elif content_lines:
                content_lines.append("")
        elif in_section == "tags" and stripped:
            for tag in stripped.split("#"):
                tag = tag.strip()
                if tag:
                    result["tags"].append(tag)

    result["content"] = "\n".join(content_lines).strip()
    return result


def publish(title: str, content: str, images: list[str] = None,
            tags: list[str] = None, auto_publish: bool = False):
    """全自动发布图文笔记到创作者中心（headless 模式）"""
    from playwright.sync_api import sync_playwright
    from playwright_stealth import Stealth

    if not COOKIE_FILE.exists():
        _p("错误：未找到创作者中心 Cookie，请先运行 login 命令。")
        return False

    screenshots = []

    _p("=" * 50)
    _p("小红书创作者中心 · 全自动发布")
    _p("=" * 50)

    _p("\n[1/6] 启动浏览器...")
    pw = sync_playwright().start()
    browser = pw.chromium.launch(headless=True)
    context = browser.new_context(
        user_agent=UA, viewport={"width": 1400, "height": 900}
    )
    cookie_str = COOKIE_FILE.read_text().strip()
    if cookie_str:
        context.add_cookies(_parse_cookie_string(cookie_str))
    page = context.new_page()
    Stealth().apply_stealth_sync(page)

    try:
        _p("[2/6] 打开发布页...")
        page.goto("https://creator.xiaohongshu.com/publish/publish",
                   wait_until="domcontentloaded", timeout=30000)
        time.sleep(3)

        if "login" in page.url.lower():
            _p("错误：Cookie 已过期，需要重新登录。")
            return False

        # Switch to image/text tab
        page.evaluate("""() => {
            const spans = document.querySelectorAll('span');
            for (const s of spans) {
                if (s.textContent.trim() === '上传图文') { s.click(); return; }
            }
        }""")
        time.sleep(2)

        # Upload images
        if images:
            _p(f"[3/6] 上传 {len(images)} 张图片...")
            file_input = page.locator('input[type="file"][accept*=".jpg"]')
            if file_input.count() == 0:
                file_input = page.locator('input[type="file"]').first
            abs_paths = [str(Path(img).resolve()) for img in images]
            file_input.set_input_files(abs_paths)
            _p(f"  文件: {', '.join(Path(p).name for p in images)}")
            time.sleep(3)
            for attempt in range(20):
                uploading = page.locator('[class*="loading"], [class*="progress"], [class*="uploading"]')
                if uploading.count() == 0:
                    break
                time.sleep(1)
            time.sleep(2)
            _p("  上传完成。")
        else:
            _p("[3/6] 无图片，跳过。")
        screenshots.append(_screenshot(page, "01_images"))

        # Fill title
        _p(f"[4/6] 填写标题: {title}")
        title_input = page.locator('input[placeholder*="标题"]')
        if title_input.count() > 0:
            title_input.first.click()
            title_input.first.fill(title)
            _p("  标题已填写。")
        else:
            _p("  警告：未找到标题输入框。")

        # Fill content body via TipTap editor
        _p("[5/6] 填写正文...")
        editor = page.locator('div.tiptap.ProseMirror, [contenteditable="true"]')
        if editor.count() > 0:
            editor.first.click()
            time.sleep(0.3)

            # Type content line by line to handle newlines properly
            for i, line in enumerate(content.split("\n")):
                if i > 0:
                    page.keyboard.press("Enter")
                if line.strip():
                    page.keyboard.type(line, delay=5)
                time.sleep(0.05)

            _p(f"  正文已填写（{len(content)} 字符）。")

            # Add tags inside the editor via topic selector popup
            if tags:
                _p("  添加话题标签...")
                page.keyboard.press("Enter")
                page.keyboard.press("Enter")
                time.sleep(0.3)

                for tag in tags[:6]:
                    page.keyboard.type(f"#{tag}", delay=30)
                    time.sleep(2)

                    # The popup is an absolutely-positioned DIV with topic items
                    selected = page.evaluate("""(tagName) => {
                        // Find the popup: absolutely positioned div containing topic text
                        const allDivs = document.querySelectorAll('div');
                        for (const div of allDivs) {
                            const style = window.getComputedStyle(div);
                            if (style.position !== 'absolute' && style.position !== 'fixed') continue;
                            const rect = div.getBoundingClientRect();
                            if (rect.width < 100 || rect.height < 50) continue;
                            const text = div.textContent || '';
                            if (!text.includes('浏览')) continue;

                            // Found the popup, now click the first item
                            const items = div.querySelectorAll('div, li, span, a');
                            for (const item of items) {
                                const iRect = item.getBoundingClientRect();
                                const iText = item.textContent.trim();
                                if (iRect.height > 20 && iRect.height < 60 &&
                                    iText.startsWith('#') && iText.includes('浏览')) {
                                    item.click();
                                    return iText.split(/\\d/)[0].trim();
                                }
                            }
                            // Fallback: click the popup's first child area
                            const firstChild = div.querySelector('div:first-child, li:first-child');
                            if (firstChild) {
                                firstChild.click();
                                return firstChild.textContent.slice(0, 30);
                            }
                        }
                        return null;
                    }""", tag)

                    if selected:
                        _p(f"    {selected.strip()} ✓")
                    else:
                        # No popup appeared, press Escape and add as plain text
                        page.keyboard.press("Escape")
                        time.sleep(0.3)
                        page.keyboard.type(" ", delay=10)
                        _p(f"    #{tag} (无弹窗，纯文本)")
                    time.sleep(0.5)
        else:
            _p("  警告：未找到正文编辑器。")

        screenshots.append(_screenshot(page, "02_content"))

        # Scroll down to see the full editor area and publish button
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        time.sleep(1)
        screenshots.append(_screenshot(page, "03_bottom"))

        # Scroll back up for full view
        page.evaluate("window.scrollTo(0, 0)")
        time.sleep(0.5)

        _p(f"\n[6/6] 内容准备完毕！")
        _p(f"\n截图文件:")
        for s in screenshots:
            _p(f"  {s}")

        if auto_publish:
            _p("\n自动发布模式，正在点击「发布」...")
            _click_publish(page)
        else:
            _p("\n等待确认发布...")
            _p(f"确认后运行: touch {SIGNAL_FILE}")
            _p("取消发布请运行: touch {SIGNAL_FILE.parent / '.cancel_publish'}")
            SIGNAL_FILE.unlink(missing_ok=True)
            cancel_file = SIGNAL_FILE.parent / ".cancel_publish"
            cancel_file.unlink(missing_ok=True)

            for i in range(300):  # 10 min timeout
                time.sleep(2)
                if SIGNAL_FILE.exists():
                    SIGNAL_FILE.unlink(missing_ok=True)
                    _p("\n收到确认信号！正在发布...")
                    _click_publish(page)
                    break
                if cancel_file.exists():
                    cancel_file.unlink(missing_ok=True)
                    _p("\n发布已取消。")
                    break
            else:
                _p("\n等待超时（10 分钟），关闭浏览器。")

        _save_cookies(context)
        return True

    except Exception as e:
        _p(f"\n发布过程出错: {e}")
        import traceback
        traceback.print_exc()
        try:
            _screenshot(page, "error")
        except Exception:
            pass
        return False
    finally:
        browser.close()
        pw.stop()


def _click_publish(page):
    """点击发布按钮"""
    clicked = page.evaluate("""() => {
        const btns = document.querySelectorAll('button');
        for (const b of btns) {
            const text = b.textContent.trim();
            if (text === '发布' || text === '发布笔记') {
                b.click();
                return text;
            }
        }
        return null;
    }""")
    if clicked:
        _p(f"已点击「{clicked}」按钮。")
        time.sleep(5)
        _screenshot(page, "04_published")
        _p("发布完成！")
    else:
        _p("警告：未找到发布按钮。")
        _screenshot(page, "04_no_button")


def main():
    parser = argparse.ArgumentParser(description="小红书创作者中心 · 发布图文笔记")
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("login", help="扫码登录创作者中心")

    pub_parser = subparsers.add_parser("publish", help="发布图文笔记")
    pub_parser.add_argument("--title", "-t", help="笔记标题")
    pub_parser.add_argument("--content", "-c", help="笔记正文")
    pub_parser.add_argument("--images", "-i", nargs="*", help="图片文件路径")
    pub_parser.add_argument("--tags", nargs="*", help="话题标签")
    pub_parser.add_argument("--draft", "-d", help="从 Markdown 草稿文件读取")
    pub_parser.add_argument("--auto", action="store_true",
                            help="跳过确认直接发布")

    args = parser.parse_args()

    if args.command == "login":
        login()
    elif args.command == "publish":
        title = args.title or ""
        content = args.content or ""
        images = args.images or []
        tags = args.tags or []

        if args.draft:
            _p(f"从草稿文件读取: {args.draft}")
            draft = _parse_draft(args.draft)
            title = title or draft["title"]
            content = content or draft["content"]
            tags = tags or draft["tags"]

        if not title:
            _p("错误：缺少标题。用 --title 指定，或用 --draft 从草稿读取。")
            sys.exit(1)
        if not content:
            _p("错误：缺少正文。用 --content 指定，或用 --draft 从草稿读取。")
            sys.exit(1)

        _p(f"标题: {title}")
        _p(f"正文: {content[:60]}...")
        _p(f"图片: {len(images)} 张")
        _p(f"标签: {', '.join(tags[:6])}")
        _p("")

        publish(title, content, images, tags, auto_publish=args.auto)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()

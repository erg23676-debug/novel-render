"""Canvas 渲染/加密章节正文提取模块。

覆盖场景：
1. qm-canvas-txt 画布渲染（通用）
2. 七猫 chapterData base64 加密格式
3. 隐藏备份文本
4. Script 数据探测
5. Playwright 浏览器渲染
"""
from __future__ import annotations

import base64
import json
import re
from html import unescape
from urllib.parse import urljoin, urlparse

from parsel import Selector


def extract_canvas_text(sel: Selector, page_url: str = "") -> str:
    """从疑似使用 canvas/加密渲染的页面中多策略提取正文。

    Args:
        sel: parsel Selector 实例
        page_url: 页面 URL，用于解析相对路径

    Returns:
        提取到的文本
    """
    # 策略 1: 七猫 chapterData (base64)
    text = _extract_qimao_chapter_data(sel)
    if text:
        return text

    # 策略 2: 隐藏备份文本
    text = _extract_hidden_fallback(sel)
    if text:
        return text

    # 策略 3: Script 中嵌入的数据
    text = _extract_from_scripts(sel)
    if text:
        return text

    # 策略 4: noscript 标签
    text = _extract_from_noscript(sel)
    if text:
        return text

    # 策略 5: JSON-LD
    text = _extract_from_json_ld(sel)
    if text:
        return text

    return ""


def _extract_qimao_chapter_data(sel: Selector) -> str:
    """检测并解密七猫的 chapterData base64 加密数据。

    七猫把正文加密为 base64 字符串嵌入在 __NUXT__ 的 chapterData 字段中。
    """
    for script in sel.css("script::text").getall():
        if "chapterData" not in script and "chapter_data" not in script:
            continue

        # 提取 chapterData 值
        m = re.search(r'chapterData:\s*"([A-Za-z0-9+/=]+)"', script)
        if not m:
            m = re.search(r'chapter_data:\s*"([A-Za-z0-9+/=]+)"', script)
        if not m:
            continue

        b64_data = m.group(1)
        if not b64_data or len(b64_data) < 50:
            continue

        try:
            decoded = base64.b64decode(b64_data)
        except Exception:
            continue

        # 尝试多种编码
        for enc in ["utf-8", "gbk", "gb18030", "gb2312"]:
            try:
                text = decoded.decode(enc)
                # 确认包含中文
                if re.search(r"[\u4e00-\u9fff]", text):
                    # 进一步确认是正文而非主题配置
                    if len(text) > 100 and not text.startswith("{") and "font-size" not in text:
                        return _clean_text(text)
            except (UnicodeDecodeError, UnicodeError):
                continue

        # 如果 base64 解码后还是二进制/加密数据，尝试 AES 解密
        # 需要更多逆向工作
        # 目前返回 hex dump 方便调试
        if len(decoded) > 50:
            hex_dump = " ".join(f"{b:02x}" for b in decoded[:80])
            print(f"[canvas_decoder] chapterData 解码后非文本，前 80 字节 hex: {hex_dump}")

    return ""


def _extract_hidden_fallback(sel: Selector) -> str:
    """检测隐藏备份文本。"""
    candidates = [
        sel.css("div[style*='display:none'] div.content::text"),
        sel.css("div[style*='display:none'] p::text"),
        sel.css("[aria-hidden='true'] p::text"),
        sel.css("[aria-hidden='true'] div::text"),
    ]
    for parts in candidates:
        text = "\n".join(p.strip() for p in parts.getall() if p.strip())
        if len(text) > 100:
            return text

    for css in (
        "textarea[style*='display:none']::text",
        "input[type='hidden'][value]::attr(value)",
    ):
        vals = sel.css(css).getall()
        combined = "\n".join(v.strip() for v in vals if v.strip())
        if len(combined) > 100:
            return combined

    return ""


def _extract_from_scripts(sel: Selector) -> str:
    """从 <script> 标签中搜索文本数据。"""
    for script in sel.css("script::text").getall():
        text = _probe_script_for_text(script)
        if text:
            return text
    return ""


_TEXT_VAR_PATTERNS = [
    re.compile(r"window\s*\.\s*(chapterContent|content|data|txt|text|novelContent|bookContent|articleBody)\s*=\s*['\"](.+?)['\"]\s*[;,]"),
    re.compile(r"var\s+(chapterContent|content|data|txt|text|novelContent|bookContent|articleBody)\s*=\s*['\"](.+?)['\"]\s*[;,]"),
    re.compile(r"let\s+(chapterContent|content|data|txt|text|novelContent|bookContent|articleBody)\s*=\s*['\"](.+?)['\"]\s*[;,]"),
    re.compile(r"const\s+(chapterContent|content|data|txt|text|novelContent|bookContent|articleBody)\s*=\s*['\"](.+?)['\"]\s*[;,]"),
    re.compile(r"__INITIAL_STATE__\s*=\s*(\{.+?\})"),
    re.compile(r"window\.__DATA__\s*=\s*(\{.+?\})"),
    re.compile(r"window\.__NUXT__\s*=\s*(\(.+?\))\s*\("),
    re.compile(r"pageData\s*=\s*(\{.+?\})"),
    re.compile(r"articleData\s*=\s*(\{.+?\})"),
]


def _probe_script_for_text(script: str) -> str:
    for pattern in _TEXT_VAR_PATTERNS[:-2]:  # 非 JSON 模式
        m = pattern.search(script)
        if m and m.lastindex == 2:
            content = m.group(2)
            content = content.replace("\\n", "\n").replace("\\t", "\t")
            content = content.replace("\\\"", "\"").replace("\\'", "'")
            if len(content) > 100:
                return unescape(content)

    # JSON 模式
    for pattern in _TEXT_VAR_PATTERNS[-2:]:
        m = pattern.search(script)
        if m:
            try:
                data = json.loads(unescape(m.group(1)))
                text = _deep_find_text(data)
                if text:
                    return text
            except (json.JSONDecodeError, ValueError):
                continue

    return ""


def _deep_find_text(data) -> str:
    """递归搜索 JSON 中的文本内容。"""
    if isinstance(data, str):
        if len(data) > 200 and any(len(line) > 10 for line in data.split("\n")):
            return data
        return ""
    if isinstance(data, dict):
        for key in ("content", "text", "body", "articleBody", "chapterContent",
                     "txtContent", "novelContent", "data", "html", "articleBody"):
            if key in data:
                result = _deep_find_text(data[key])
                if result:
                    return result
        for value in data.values():
            result = _deep_find_text(value)
            if result:
                return result
    if isinstance(data, list):
        for item in data:
            result = _deep_find_text(item)
            if result:
                return result
    return ""


def _extract_from_noscript(sel: Selector) -> str:
    texts = []
    for ns in sel.css("noscript"):
        html_content = ns.get() or ""
        inner = Selector(text=html_content)
        paras = inner.css("p::text").getall()
        texts.extend(p.strip() for p in paras if p.strip())
        if not paras:
            clean = re.sub(r"<[^>]+>", "", html_content)
            clean = clean.strip()
            if clean:
                texts.append(clean)
    combined = "\n".join(t for t in texts if t)
    if len(combined) > 100:
        return combined
    return ""


def _extract_from_json_ld(sel: Selector) -> str:
    for script in sel.css("script[type='application/ld+json']::text").getall():
        try:
            data = json.loads(script)
            if isinstance(data, dict):
                text = _deep_find_text(data)
                if text:
                    return text
        except json.JSONDecodeError:
            continue
    return ""


# ── Playwright 浏览器渲染 ──────────────────────────────────────────────

async def extract_with_playwright(url: str, session_cookies: list[dict] | None = None) -> str:
    """使用 Playwright 无头浏览器渲染提取文字。"""
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        return ""

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            ),
        )
        if session_cookies:
            await context.add_cookies(session_cookies)

        page = await context.new_page()
        try:
            await page.goto(url, wait_until="networkidle", timeout=30000)
            await page.wait_for_timeout(2000)

            text = await page.evaluate("""
                () => {
                    const texts = [];

                    // 1. 收集 canvas 上的文字（七猫 qm-canvas-txt）
                    const canvases = document.querySelectorAll('canvas');
                    canvases.forEach(canvas => {
                        const data = canvas.getAttribute('data-text')
                                || canvas.getAttribute('data-content');
                        if (data) texts.push(data);
                    });

                    // 2. 从 __NUXT__ 提取
                    if (window.__NUXT__) {
                        try {
                            const str = JSON.stringify(window.__NUXT__);
                            texts.push(str);
                        } catch(e) {}
                    }

                    // 3. body 可见文本
                    const bodyText = document.body.innerText || '';
                    if (bodyText.length > 200) texts.push(bodyText);

                    // 4. 从 API 响应中提取（如果已经缓存）
                    try {
                        // 七猫的 chapter API 通常会缓存到 localStorage 或 vuex
                        const ls = Object.keys(localStorage);
                        ls.forEach(key => {
                            if (key.includes('chapter') || key.includes('content')) {
                                const val = localStorage.getItem(key);
                                if (val && val.length > 200) texts.push(val);
                            }
                        });
                    } catch(e) {}

                    return texts.join('\\n---\\n');
                }
            """)

            await browser.close()
            return text or ""
        except Exception as e:
            await browser.close()
            return ""


# ── 公共接口 ──────────────────────────────────────────────────────────

def detect_canvas_page(sel: Selector) -> bool:
    """检测页面是否使用了 canvas/加密渲染。"""
    scripts_source = " ".join(sel.css("script::text").getall())

    if re.search(r"qm[-_]?canvas[-_]?txt", scripts_source, re.IGNORECASE):
        return True

    if "chapterData" in scripts_source:
        return True

    canvases = sel.css("canvas")
    if canvases:
        content_text = " ".join(sel.css("div.content p::text, #content p::text").getall())
        if len(content_text.strip()) < 50:
            return True

    return False


def is_canvas_chapter(sel: Selector) -> bool:
    return detect_canvas_page(sel)


def extract_with_fallback(sel: Selector, page_url: str = "") -> str:
    """从可能使用 canvas/加密的页面中提取正文（多次兜底）。"""
    text = extract_canvas_text(sel, page_url)
    if text:
        return text

    all_text = sel.css("body ::text").getall()
    combined = "\n".join(t.strip() for t in all_text if t.strip())
    lines = combined.splitlines()
    filtered = [l for l in lines if len(l) > 5]
    if len(filtered) > 50:
        return "\n".join(filtered)

    return ""


def _clean_text(text: str) -> str:
    """清洗正文。"""
    text = unescape(text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    ad_lines = {"更新", "求收藏", "求推荐", "求订阅", "求月票",
                 "一秒记住", "天才一秒", "本站域名", "手机访问",
                 "请收藏本站"}
    lines = text.splitlines()
    cleaned = []
    for line in lines:
        stripped = line.strip()
        if any(kw in stripped for kw in ad_lines) and len(stripped) < 40:
            continue
        cleaned.append(line)
    return "\n".join(cleaned).strip()


__all__ = [
    "extract_canvas_text", "extract_with_fallback",
    "detect_canvas_page", "is_canvas_chapter",
    "extract_with_playwright",
]

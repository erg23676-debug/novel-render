"""动态网站适配器 —— 输入任意网站小说 URL，自动适配。

工作原理：
  1. 用户输入书籍详情页/目录页 URL，程序抓取 HTML。
  2. 通过一组"通用探测器"尝试提取：书名、作者、章节目录、正文。
  3. 支持 canvas 渲染（qm-canvas-txt 反爬）章节的文字提取。
  4. Cookie 由外部 Session 统一管理（用户粘贴的登录态）。
  5. VIP/付费章节抬起 ChapterLockedError，不解密不绕过。

依赖：parsel（已含）、requests（已含）。
"""
from __future__ import annotations

import json
import re
from html import unescape
from urllib.parse import urljoin, urlparse

from parsel import Selector

from core.session import Session
from core.source_base import ChapterLockedError, DynamicWebsiteSource, SourceError
from core.sources.canvas_decoder import (
    extract_canvas_text,
    extract_with_fallback,
    is_canvas_chapter,
)
from models import Book, Chapter

# 常见的小说站点目录页 URL 模式（用于识别目录页 vs 详情页 vs 正文页）
_CHAPTER_PATTERNS = re.compile(
    r"(第[\d零一二三四五六七八九十百千两]+[章卷回节])", re.IGNORECASE
)


class WebsiteDynamicSource(DynamicWebsiteSource):
    """通用动态网站源：输入 URL 自动解析书籍信息和章节。"""

    name: str = "dynamic"

    def __init__(self, session: Session, domain: str, base_url: str) -> None:
        super().__init__(session, domain, base_url)
        self._chapters_cache: dict[str, list[Chapter]] = {}
        self._book_cache: dict[str, Book] = {}

    # ── 搜索 ──────────────────────────────────────────────────────────
    def search(self, keyword: str) -> list[Book]:
        if keyword.startswith("http://") or keyword.startswith("https://"):
            return self._parse_url_as_book(keyword)
        return []

    # ── 目录解析 ──────────────────────────────────────────────────────
    def get_chapters(self, book: Book) -> list[Chapter]:
        if book.book_id in self._chapters_cache:
            return self._chapters_cache[book.book_id]

        url = book.url or f"{self.base_url}/book/{book.book_id}"
        resp = self.session.get(url)
        sel = Selector(resp.text)

        chapters = self._try_extract_chapters(sel, book, url)
        if not chapters:
            raise SourceError(f"未能从 {url} 解析出章节目录，可能该页面不是目录页/详情页")

        self._chapters_cache[book.book_id] = chapters
        self._book_cache[book.book_id] = book
        return chapters

    def _try_extract_chapters(self, sel: Selector, book: Book, url: str) -> list[Chapter]:
        """多策略尝试提取章节目录。"""
        extractors = [
            self._extract_v1_common,
            self._extract_v2_links_with_chapter_keywords,
            self._extract_v3_all_links_on_page,
        ]
        for extractor in extractors:
            chapters = extractor(sel, book, url)
            if len(chapters) >= 3:
                return chapters
        return []

    def _extract_v1_common(self, sel: Selector, book: Book, url: str) -> list[Chapter]:
        """通用选择器：尝试常见的目录结构。"""
        candidates = [
            sel.css("ul.chapter-list li a"),
            sel.css("div.chapter-list a"),
            sel.css("div#list a"),
            sel.css("div.book-list a"),
            sel.css("dd a"),
            sel.css("li a"),
        ]
        for links in candidates:
            chapters = self._links_to_chapters(links, book, url)
            if len(chapters) >= 3:
                return chapters
        return []

    def _extract_v2_links_with_chapter_keywords(self, sel: Selector, book: Book, url: str) -> list[Chapter]:
        """通过匹配链接文本中的"第X章"关键词提取章节目录。"""
        links = sel.css("a")
        chapter_links = []
        for link in links:
            text = link.css("::text").get("")
            if _CHAPTER_PATTERNS.search(text):
                chapter_links.append(link)
        if len(chapter_links) >= 3:
            return self._links_to_chapters(chapter_links, book, url)
        return []

    def _extract_v3_all_links_on_page(self, sel: Selector, book: Book, url: str) -> list[Chapter]:
        """兜底策略：提取所有链接，过滤掉明显不相关的。"""
        links = sel.css("a")
        skip_words = {"登录", "注册", "搜索", "首页", "上一页", "下一页",
                       "上一章", "下一章", "全部章节", "RSS", "订阅",
                       "login", "register", "search", "home", "prev", "next"}
        chapter_links = []
        for link in links:
            text = link.css("::text").get("")
            href = link.css("::attr(href)").get("")
            if not text or not href:
                continue
            text = text.strip()
            if not text or len(text) < 2:
                continue
            if text in skip_words:
                continue
            if href.startswith("#") or href.startswith("javascript:"):
                continue
            chapter_links.append(link)
        if len(chapter_links) >= 5:
            return self._links_to_chapters(chapter_links, book, url)
        return []

    def _links_to_chapters(self, links: list, book: Book, base_url: str) -> list[Chapter]:
        """将 CSS 选择器结果转换为 Chapter 列表。"""
        chapters = []
        seen = set()
        for i, link in enumerate(links):
            href = link.css("::attr(href)").get("")
            text = link.css("::text").get("")
            if not href or not text:
                continue
            text = text.strip()
            if not text:
                continue
            full_url = urljoin(base_url, href)
            if full_url in seen:
                continue
            seen.add(full_url)
            is_vip = bool(link.css(".vip, .lock, .paid, [class*=vip], [class*=lock]"))
            chapters.append(Chapter(
                book_key=book.key,
                index=len(chapters),
                title=text,
                chapter_id=full_url.rstrip("/").rsplit("/", 1)[-1],
                url=full_url,
                is_vip=is_vip,
            ))
        return chapters

    # ── 正文提取（含 Canvas 支持） ──────────────────────────────────
    def get_content(self, chapter: Chapter) -> str:
        resp = self.session.get(chapter.url)
        sel = Selector(resp.text)

        # VIP 检测
        locked_hint = sel.css(
            ".need-login, .buy-chapter, .vip-mask, "
            "[class*=locked], [class*=lock], .chapter-locked"
        )
        if locked_hint:
            raise ChapterLockedError("该章节需要登录或购买后才能阅读")

        # 检测是否使用 canvas 渲染（如 qm-canvas-txt）
        uses_canvas = is_canvas_chapter(sel)
        if uses_canvas:
            text = self._extract_canvas_content(sel, chapter)
        else:
            text = self._try_extract_content(sel)

        if text:
            return text

        # 最后兜底
        text = extract_with_fallback(sel, chapter.url)
        if text:
            return text

        raise SourceError(f"正文解析为空，URL: {chapter.url}")

    def _extract_canvas_content(self, sel: Selector, chapter: Chapter) -> str:
        """处理使用 canvas 渲染的反爬章节。"""
        text = extract_canvas_text(sel, chapter.url)
        if text:
            return text
        text = self._extract_from_json_ld(sel)
        if text:
            return text
        return ""

    def _extract_from_json_ld(self, sel: Selector) -> str:
        """从 JSON-LD 结构化数据中提取正文。"""
        for script in sel.css("script[type='application/ld+json']::text").getall():
            try:
                data = json.loads(script)
                if isinstance(data, dict):
                    text = self._deep_find_text(data)
                    if text:
                        return text
            except json.JSONDecodeError:
                continue
        return ""

    @staticmethod
    def _deep_find_text(data) -> str:
        """递归搜索 JSON 对象中的文本内容。"""
        if isinstance(data, str):
            if len(data) > 200 and any(len(line) > 10 for line in data.split("\n")):
                return data
            return ""
        if isinstance(data, dict):
            for key in ("articleBody", "content", "text", "description",
                         "chapterContent", "body"):
                if key in data:
                    result = WebsiteDynamicSource._deep_find_text(data[key])
                    if result:
                        return result
            for value in data.values():
                result = WebsiteDynamicSource._deep_find_text(value)
                if result:
                    return result
        if isinstance(data, list):
            for item in data:
                result = WebsiteDynamicSource._deep_find_text(item)
                if result:
                    return result
        return ""

    def _try_extract_content(self, sel: Selector) -> str:
        """多策略提取正文（常规 HTML 提取）。"""
        strategies = [
            "div.content p::text",
            "div#content p::text",
            "div#booktxt p::text",
            "div#BookTxt p::text",
            "div.read-content p::text",
            "div#chaptercontent p::text",
            "div.chapter-content p::text",
            "article p::text",
            "div.txt p::text",
            "p::text",
        ]
        for css_sel in strategies:
            parts = sel.css(css_sel).getall()
            text = "\n".join(p.strip() for p in parts if p.strip())
            if len(text) > 100:
                return self._clean_text(text)
        return ""

    @staticmethod
    def _clean_text(text: str) -> str:
        """清洗正文：解 HTML 转义、合并空行、去除广告残留。"""
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


# ── 工厂函数 ──────────────────────────────────────────────────────────
def create_dynamic_source(session: Session, url: str) -> WebsiteDynamicSource | None:
    """从 URL 创建动态网站源。"""
    parsed = urlparse(url)
    if not parsed.netloc:
        return None
    domain = parsed.netloc
    base_url = f"{parsed.scheme}://{parsed.netloc}"
    return WebsiteDynamicSource(session, domain, base_url)


def register_domain_source(session: Session, sources: dict, url: str) -> str | None:
    """动态注册一个域名源到 sources 字典。

    Args:
        session: Session 实例
        sources: {name: source} 字典（会原地修改）
        url: 用户输入的 URL

    Returns:
        source 名字（如 "dynamic:www.example.com"），失败返回 None
    """
    parsed = urlparse(url)
    if not parsed.netloc:
        return None
    domain = parsed.netloc
    source_name = f"dynamic:{domain}"

    if source_name in sources:
        return source_name

    src = WebsiteDynamicSource(session, domain, f"{parsed.scheme}://{parsed.netloc}")
    sources[source_name] = src
    return source_name


__all__ = [
    "WebsiteDynamicSource", "create_dynamic_source", "register_domain_source",
]

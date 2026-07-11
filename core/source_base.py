"""站点适配器抽象基类 + 动态源管理器。

接入一个新站点 = 继承 BaseSource，实现 search / get_chapters / get_content 三个方法，
或通过 URL 输入在运行时动态注册一个域名源。
其余（UI、历史、翻页）全部通用。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from urllib.parse import urlparse

import requests
from parsel import Selector

from models import Book, Chapter


class SourceError(Exception):
    """站点解析/网络类错误。"""


class ChapterLockedError(SourceError):
    """章节需要登录或购买才能阅读（VIP 未解锁）。

    ——这是"VIP 预留位"的合法边界：程序在此停下并提示用户去登录/购买，
    绝不尝试解密或绕过付费墙。
    """


class BaseSource(ABC):
    """站点适配器抽象基类。"""

    name: str = "base"

    def __init__(self, session: object | None = None) -> None:
        self.session = session

    @abstractmethod
    def search(self, keyword: str) -> list[Book]:
        """按关键词搜索，返回书籍列表。"""

    @abstractmethod
    def get_chapters(self, book: Book) -> list[Chapter]:
        """返回某本书的完整有序章节目录。"""

    @abstractmethod
    def get_content(self, chapter: Chapter) -> str:
        """返回章节正文纯文本。

        实现约定：
          - 免费或"用当前登录态已解锁"的章节 -> 正常返回正文。
          - VIP 且未解锁 -> raise ChapterLockedError（不要返回残缺/加密内容）。
        """


# ── 动态域名源（基类，具体实现在 website_dynamic.py） ────────────────────

class DynamicWebsiteSource(BaseSource):
    """运行时根据用户输入的 URL 动态创建的网站源（基类）。

    具体实现在 WebsiteDynamicSource（website_dynamic.py）中。
    """

    name: str = "dynamic"

    def __init__(self, session: object, domain: str, base_url: str) -> None:
        if session is None:
            from core.session import Session
            session = Session()
        super().__init__(session)
        self.domain = domain
        self.base_url = base_url

    def search(self, keyword: str) -> list[Book]:
        """尝试将 URL 关键词解析为一本书。"""
        if keyword.startswith("http://") or keyword.startswith("https://"):
            return self._parse_url_as_book(keyword)
        return []

    def _parse_url_as_book(self, url: str) -> list[Book]:
        """从 URL 页面尝试提取书籍信息。"""
        try:
            resp = self.session.get(url)
            sel = Selector(resp.text)
            title = (
                sel.css("h1::text").get("")
                or sel.css("meta[property='og:title']::attr(content)").get("")
                or sel.css("title::text").get("")
                or self.domain
            ).strip()
            author = (
                sel.css(".author::text").get("")
                or sel.css("meta[property='og:novel:author']::attr(content)").get("")
                or sel.css("meta[name='author']::attr(content)").get("")
                or ""
            ).strip()
            book_id = url.rstrip("/").rsplit("/", 1)[-1] or self.domain
            return [Book(
                source=f"dynamic:{self.domain}",
                book_id=book_id,
                title=title,
                author=author,
                url=url,
            )]
        except requests.RequestException:
            return []

    def get_chapters(self, book: Book) -> list[Chapter]:
        raise NotImplementedError("DynamicWebsiteSource.get_chapters 应由子类覆盖")

    def get_content(self, chapter: Chapter) -> str:
        raise NotImplementedError("DynamicWebsiteSource.get_content 应由子类覆盖")


__all__ = [
    "BaseSource", "SourceError", "ChapterLockedError", "DynamicWebsiteSource",
]

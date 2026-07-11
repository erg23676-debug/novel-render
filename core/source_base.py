"""站点适配器抽象基类。

接入一个新站点 = 继承 BaseSource，实现 search / get_chapters / get_content 三个方法。
其余（UI、历史、翻页）全部通用。
"""
from __future__ import annotations

from abc import ABC, abstractmethod

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


__all__ = [
    "BaseSource", "SourceError", "ChapterLockedError",
]

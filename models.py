"""数据模型：Book / Chapter。所有站点适配器都返回这些统一结构。"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Book:
    source: str            # 适配器名字，如 "local" / "example"
    book_id: str           # 站点内唯一 id
    title: str
    author: str = ""
    cover: str = ""        # 封面 url（可选）
    intro: str = ""        # 简介（可选）
    url: str = ""          # 书籍详情页 url（可选）

    @property
    def key(self) -> str:
        return f"{self.source}:{self.book_id}"


@dataclass
class Chapter:
    book_key: str          # 归属 Book.key
    index: int             # 在目录中的序号，从 0 开始
    title: str
    chapter_id: str = ""   # 站点内章节 id
    url: str = ""          # 正文页 url（可选）
    is_vip: bool = False   # 是否 VIP/付费章节

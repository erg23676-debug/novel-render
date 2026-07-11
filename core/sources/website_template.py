"""网站适配器模板 —— 你给了域名后，在这里填三个方法即可。

用法：
  1) 把 BASE 改成目标站点域名；
  2) 用浏览器 F12 看搜索接口 / 目录页 / 正文页的真实结构，
     照着填 search / get_chapters / get_content 的解析逻辑；
  3) VIP：正文页若显示"需登录/购买"，就 raise ChapterLockedError，
     不要在这里写任何解密或绕过逻辑。

完整可用的动态适配器在 website_dynamic.py，支持输入 URL 自动适配。
"""
from __future__ import annotations

from urllib.parse import urljoin

from parsel import Selector

from models import Book, Chapter
from core.source_base import BaseSource, ChapterLockedError, SourceError

BASE = "https://example.com"  # TODO: 改成目标站点域名


class WebsiteSource(BaseSource):
    name = "website"

    def search(self, keyword: str) -> list[Book]:
        # TODO: 换成站点真实的搜索 url / 参数
        resp = self.session.get(f"{BASE}/search", params={"q": keyword})
        if resp.status_code != 200:
            raise SourceError(f"搜索失败: HTTP {resp.status_code}")
        sel = Selector(resp.text)
        books = []
        # TODO: 换成真实的结果条目选择器
        for node in sel.css("div.book-item"):
            href = node.css("a::attr(href)").get() or ""
            books.append(Book(
                source=self.name,
                book_id=href.rstrip("/").split("/")[-1],
                title=(node.css("a::text").get() or "").strip(),
                author=(node.css(".author::text").get() or "").strip(),
                url=urljoin(BASE, href),
            ))
        return books

    def get_chapters(self, book: Book) -> list[Chapter]:
        resp = self.session.get(book.url or f"{BASE}/book/{book.book_id}")
        sel = Selector(resp.text)
        chapters = []
        # TODO: 换成真实的目录条目选择器
        for i, node in enumerate(sel.css("ul.chapter-list li a")):
            href = node.css("::attr(href)").get() or ""
            # 站点常用某个 class/图标标记 VIP，这里按需判断
            is_vip = bool(node.css(".vip, .lock"))
            chapters.append(Chapter(
                book_key=book.key,
                index=i,
                title=(node.css("::text").get() or "").strip(),
                chapter_id=href.rstrip("/").split("/")[-1],
                url=urljoin(BASE, href),
                is_vip=is_vip,
            ))
        return chapters

    def get_content(self, chapter: Chapter) -> str:
        resp = self.session.get(chapter.url)
        sel = Selector(resp.text)

        # —— VIP 合法边界：检测"需登录/购买"的提示，命中就停下，不解密。
        locked_hint = sel.css(".need-login, .buy-chapter, .vip-mask")
        if locked_hint:
            raise ChapterLockedError("该章节需要登录或购买后才能阅读")

        # TODO: 换成真实的正文选择器
        paras = sel.css("div.content p::text").getall()
        text = "\n".join(p.strip() for p in paras if p.strip())
        if not text:
            raise SourceError("正文解析为空，检查选择器")
        return text

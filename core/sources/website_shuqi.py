"""书旗小说移动站 (t.shuqi.com) 适配器。

搜索、目录和正文均使用移动站前端实际调用的接口。只读取站点判定为
免费或当前会话已购买的章节，未解锁章节按统一约定抛出
ChapterLockedError。
"""
from __future__ import annotations

import base64
import codecs
import hashlib
import html as html_module
import re
import time

from core.session import Session
from core.source_base import (
    BaseSource,
    ChapterLockedError,
    SourceError,
)
from models import Book, Chapter


class ShuqiSource(BaseSource):
    """书旗小说移动站适配器。"""

    name = "shuqi"
    SEARCH_API = "https://read.xiaoshuo1-sm.com/novel/i.php"
    CATALOG_API = "https://content.shuqireader.com/openapi/book/chapterlist"
    CONTENT_SIGN_KEY = "37e81a9d8f02596e1b895d07c171d5c9"
    MOBILE_BASE = "https://t.shuqi.com"

    def __init__(self, session: Session) -> None:
        super().__init__(session)
        self._chapters_cache: dict[str, list[Chapter]] = {}
        self._book_meta: dict[str, dict] = {}
        self._chapter_meta: dict[tuple[str, str], dict] = {}

    # ── 搜索 ──────────────────────────────────────────────────────────
    def search(self, keyword: str) -> list[Book]:
        keyword = keyword.strip()
        if not keyword:
            return []
        try:
            resp = self.session.get(
                self.SEARCH_API,
                params={
                    "do": "is_search",
                    "q": keyword,
                    "page": 1,
                    "size": 15,
                    "uid": 8000000,
                    "platform": 3,
                    "p": 3,
                    "filterMigu": 1,
                    "ver": "",
                },
                headers={"Referer": f"{self.MOBILE_BASE}/search?history=%2F"},
            )
            self._check_response(resp, "搜索")
            data = resp.json()
        except SourceError:
            raise
        except Exception as exc:
            raise SourceError(f"书旗搜索失败: {exc}") from exc
        return self._parse_search(data)

    def _parse_search(self, data: dict) -> list[Book]:
        items: list[dict] = []
        if isinstance(data.get("aladdin"), dict):
            items.append(data["aladdin"])
        items.extend(x for x in (data.get("data") or []) if isinstance(x, dict))

        books: list[Book] = []
        seen: set[str] = set()
        for item in items:
            bid = str(item.get("bid") or item.get("bookId") or "")
            title = str(item.get("title") or item.get("bookName") or "").strip()
            if not bid or not title or bid in seen:
                continue
            seen.add(bid)
            cover = str(item.get("cover") or "")
            if cover.startswith("http://"):
                cover = "https://" + cover[7:]
            books.append(Book(
                source=self.name,
                book_id=bid,
                title=title,
                author=str(item.get("author") or item.get("authorName") or ""),
                cover=cover,
                intro=str(item.get("desc") or "").strip(),
                url=f"{self.MOBILE_BASE}/book/{bid}",
            ))
        return books

    # ── 目录 ──────────────────────────────────────────────────────────
    def get_chapters(self, book: Book) -> list[Chapter]:
        if book.book_id in self._chapters_cache:
            return self._chapters_cache[book.book_id]
        data = self._load_mobile_catalog(book.book_id)
        chapters = self._chapters_from_catalog_data(book, data)
        if not chapters:
            raise SourceError(f"无法获取《{book.title}》的章节目录")
        self._chapters_cache[book.book_id] = chapters
        return chapters

    def _load_mobile_catalog(self, book_id: str) -> dict:
        """调用书旗移动阅读器使用的签名目录接口。"""
        timestamp = int(time.time())
        values = {
            "bookId": book_id,
            "timestamp": timestamp,
            "user_id": 8000000,
        }
        sign_text = "".join(str(values[key]) for key in sorted(values))
        sign = hashlib.md5(
            (sign_text + self.CONTENT_SIGN_KEY).encode()
        ).hexdigest()
        try:
            resp = self.session.get(
                self.CATALOG_API,
                params={
                    **values,
                    "sign": sign,
                    "platform": 0,
                },
                headers={"Referer": f"{self.MOBILE_BASE}/reader/{book_id}"},
            )
            self._check_response(resp, "目录")
            payload = resp.json()
            if str(payload.get("state")) != "200":
                raise SourceError(
                    f"书旗目录获取失败: {payload.get('message') or '未知错误'}"
                )
            data = payload.get("data")
            if not isinstance(data, dict) or not data.get("chapterList"):
                raise SourceError("书旗移动端未返回章节列表")
        except SourceError:
            raise
        except Exception as exc:
            raise SourceError(f"书旗移动端目录请求失败: {exc}") from exc
        self._cache_catalog_data(book_id, data)
        return data

    def _cache_catalog_data(self, book_id: str, data: dict) -> None:
        self._book_meta[book_id] = {
            "freeContUrlPrefix": self._https_url(data.get("freeContUrlPrefix", "")),
            "chargeContUrlPrefix": self._https_url(data.get("chargeContUrlPrefix", "")),
            "shortContUrlPrefix": self._https_url(data.get("shortContUrlPrefix", "")),
        }
        for volume in data.get("chapterList") or []:
            for item in volume.get("volumeList") or []:
                cid = str(item.get("chapterId") or "")
                if cid:
                    self._chapter_meta[(book_id, cid)] = item

    def _chapters_from_catalog_data(self, book: Book, data: dict) -> list[Chapter]:
        result: list[Chapter] = []
        for volume in data.get("chapterList") or []:
            for item in volume.get("volumeList") or []:
                cid = str(item.get("chapterId") or "")
                if not cid:
                    continue
                readable = bool(item.get("isFreeRead") or item.get("isBuy"))
                result.append(Chapter(
                    book_key=book.key,
                    index=len(result),
                    title=str(item.get("chapterName") or f"第{len(result) + 1}章"),
                    chapter_id=cid,
                    url=(f"{self.MOBILE_BASE}/reader/{book.book_id}"
                         f"?forceChapterId={cid}"),
                    is_vip=not readable,
                ))
        return result

    # ── 正文 ──────────────────────────────────────────────────────────
    def get_content(self, chapter: Chapter) -> str:
        book_id = chapter.book_key.split(":", 1)[1]
        key = (book_id, chapter.chapter_id)
        if key not in self._chapter_meta:
            self._load_mobile_catalog(book_id)
        meta = self._chapter_meta.get(key)
        if not meta:
            raise SourceError(f"找不到章节数据: {chapter.title}")

        is_free = bool(meta.get("isFreeRead"))
        is_bought = bool(meta.get("isBuy"))
        if not (is_free or is_bought):
            raise ChapterLockedError(
                f"《{chapter.title}》在书旗当前仍是锁定章节，请在官方页面解锁后阅读。"
            )

        book_meta = self._book_meta.get(book_id, {})
        prefix_key = "freeContUrlPrefix" if is_free else "chargeContUrlPrefix"
        prefix = str(book_meta.get(prefix_key) or "")
        suffix = html_module.unescape(str(meta.get("contUrlSuffix") or ""))
        if not prefix or not suffix:
            raise SourceError(f"章节正文地址缺失: {chapter.title}")

        try:
            resp = self.session.get(
                prefix + suffix,
                headers={"Referer": chapter.url or f"{self.MOBILE_BASE}/reader/{book_id}"},
            )
            self._check_response(resp, "正文")
            payload = resp.json()
            encoded = payload.get("ChapterContent") or payload.get("chapterContent")
            if not isinstance(encoded, str) or not encoded:
                message = payload.get("message") or payload.get("info") or "正文为空"
                raise SourceError(f"书旗正文获取失败: {message}")
            return self._decode_content(encoded)
        except SourceError:
            raise
        except Exception as exc:
            raise SourceError(f"书旗正文获取失败: {exc}") from exc

    @staticmethod
    def _decode_content(encoded: str) -> str:
        """按移动阅读器声明的 rot13 -> base64 -> trim 顺序处理正文。"""
        try:
            rotated = codecs.decode(encoded, "rot_13")
            raw = base64.b64decode(rotated).decode("utf-8")
        except Exception as exc:
            raise SourceError(f"书旗正文解码失败: {exc}") from exc
        raw = re.sub(r"<br\s*/?>", "\n", raw, flags=re.IGNORECASE)
        raw = re.sub(r"</p\s*>", "\n", raw, flags=re.IGNORECASE)
        raw = re.sub(r"<[^>]+>", "", raw)
        text = html_module.unescape(raw).replace("\u3000", " ")
        text = "\n".join(line.strip() for line in text.splitlines())
        return re.sub(r"\n{3,}", "\n\n", text).strip()

    @staticmethod
    def _check_response(resp, action: str) -> None:
        if resp.status_code == 429:
            raise SourceError(f"书旗{action}请求过于频繁，请稍后重试")
        if resp.status_code != 200:
            raise SourceError(f"书旗{action}请求失败: HTTP {resp.status_code}")

    @staticmethod
    def _https_url(url: object) -> str:
        value = str(url or "")
        return "https://" + value[7:] if value.startswith("http://") else value


def register_shuqi(session: Session, sources: dict) -> str:
    name = ShuqiSource.name
    if name not in sources:
        sources[name] = ShuqiSource(session)
    return name


__all__ = ["ShuqiSource", "register_shuqi"]

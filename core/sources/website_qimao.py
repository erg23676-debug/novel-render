"""七猫中文网 (qimao.com) 适配器。

API 端点:
  search:   GET  https://www.qimao.com/qimaoapi/api/search/result
  catalog:  GET  https://www.qimao.com/qimaoapi/api/book/chapter-list
  detail:   GET  https://api-bc.wtzw.com/api/v1/reader/detail (签名)
  content:  GET  https://api-ks.wtzw.com/api/v1/chapter/content (签名)

签名算法: MD5(key排序拼接 + d3dGiJc651gSQ8w1)
"""
from __future__ import annotations

import hashlib
import html as html_module
import json
import re
from html import unescape

import requests

from core.session import Session
from core.source_base import ChapterLockedError, DynamicWebsiteSource, SourceError
from models import Book, Chapter

SIGN_KEY = "d3dGiJc651gSQ8w1"


def _sign_params(params: dict) -> dict:
    keys = sorted(params.keys())
    sign_str = "".join(k + "=" + str(params[k]) for k in keys) + SIGN_KEY
    params["sign"] = hashlib.md5(sign_str.encode()).hexdigest()
    return params


def _make_headers() -> dict:
    headers = {
        "AUTHORIZATION": "",
        "app-version": "73720",
        "application-id": "com.****.reader",
        "channel": "unknown",
        "net-env": "1",
        "platform": "android",
        "qm-params": "",
        "reg": "0",
    }
    keys = sorted(headers.keys())
    sign_str = "".join(k + "=" + str(headers[k]) for k in keys) + SIGN_KEY
    headers["sign"] = hashlib.md5(sign_str.encode()).hexdigest()
    return headers


class QimaoSource(DynamicWebsiteSource):
    """七猫中文网适配器。"""

    name: str = "qimao"

    def __init__(self, session: Session) -> None:
        super().__init__(session, "www.qimao.com", "https://www.qimao.com")
        self._chapters_cache: dict[str, list[Chapter]] = {}
        self._http = requests.Session()
        self._http.headers.update({"User-Agent": "okhttp/4.12.0"})
        # 缓存 content_md5
        self._content_md5_cache: dict[str, str] = {}

    # ── 搜索 ──────────────────────────────────────────────────────────
    def search(self, keyword: str) -> list[Book]:
        if keyword.startswith("http"):
            return self._parse_url_as_book(keyword)
        try:
            resp = self.session.get(
                "https://www.qimao.com/qimaoapi/api/search/result",
                params={"keyword": keyword, "page": "1", "page_size": "15"},
            )
            if resp.status_code == 200:
                data = resp.json()
                return self._parse_search_api(data)
        except Exception:
            pass
        return []

    def _parse_search_api(self, data: dict) -> list[Book]:
        books = []
        for item in (data.get("data", {}).get("search_list", []) or data.get("search_list", [])):
            bid = str(item.get("book_id", ""))
            books.append(Book(
                source=self.name, book_id=bid,
                title=str(item.get("title", "")),
                author=str(item.get("author", "")),
                url=f"https://www.qimao.com/shuku/{bid}/",
            ))
        return books

    # ── 目录 ──────────────────────────────────────────────────────────
    def get_chapters(self, book: Book) -> list[Chapter]:
        if book.book_id in self._chapters_cache:
            return self._chapters_cache[book.book_id]
        chapters = self._fetch_chapters_from_api(book)
        if not chapters:
            raise SourceError(f"无法获取 {book.title} 的章节目录")
        self._chapters_cache[book.book_id] = chapters
        return chapters

    def _fetch_chapters_from_api(self, book: Book) -> list[Chapter]:
        try:
            resp = self.session.get(
                "https://www.qimao.com/qimaoapi/api/book/chapter-list",
                params={"book_id": book.book_id},
            )
            if resp.status_code != 200:
                return []
            data = resp.json()
            chapters_data = data.get("data", {}).get("chapters", []) or data.get("chapters", [])
            return [
                Chapter(
                    book_key=book.key, index=i,
                    title=str(ch.get("title", "")),
                    chapter_id=str(ch.get("id", "")),
                    url=f"https://www.qimao.com/shuku/{book.book_id}-{ch.get('id', '')}/",
                    is_vip=ch.get("is_vip", "0") not in ("0", "", False, None),
                )
                for i, ch in enumerate(chapters_data)
            ]
        except Exception:
            return []

    # ── 正文获取 ──────────────────────────────────────────────────────
    def get_content(self, chapter: Chapter) -> str:
        book_id = chapter.book_key.split(":", 1)[1]

        # 尝试: APP API 获取正文
        try:
            text = self._fetch_content_via_api(book_id, chapter.chapter_id)
            if text:
                return self._clean_text(text)
        except ChapterLockedError:
            raise
        except Exception:
            pass

        # 兜底: 网页版免费章节
        try:
            text = self._fetch_content_from_web(chapter)
            if text:
                return self._clean_text(text)
        except ChapterLockedError:
            raise
        except Exception:
            pass

        raise SourceError(f"正文获取失败: {chapter.url}")

    def _fetch_content_via_api(self, book_id: str, chapter_id: str) -> str:
        """通过七猫 APP content API 获取章节正文（含解密）。"""
        params = _sign_params({"id": book_id, "chapterId": chapter_id})
        headers = _make_headers()

        resp = self._http.get(
            "https://api-ks.wtzw.com/api/v1/chapter/content",
            params=params, headers=headers, timeout=15,
        )
        if resp.status_code != 200:
            return ""

        data = resp.json()
        err = data.get("errors", {})
        code = err.get("code", "0")
        if code not in ("0", ""):
            if code == "44010102":
                raise SourceError("章节内容 API 参数错误")
            return ""

        encrypted_b64 = data.get("data", {}).get("content", "")
        if not encrypted_b64:
            return ""

        # base64 解码
        import base64
        raw = base64.b64decode(encrypted_b64)

        # 格式: 19字节 header + 加密正文
        header_bytes = raw[:19]
        encrypted_body = raw[19:]
        header_num = header_bytes[:16].decode("ascii")
        marker = header_bytes[16:]

        # 解密
        text = self._decrypt_content(encrypted_body, header_num, marker, chapter_id, book_id)
        if text:
            return text

        return ""

    def _decrypt_content(self, data: bytes, header_num: str, marker: bytes,
                          chapter_id: str, book_id: str) -> str:
        """解密章节内容。

        七猫加密方案: AES-128-CBC / NoPadding
          Key: 固定硬编码 b"242ccb8230d709e1"
          IV:  header_num (16位数字的 ASCII)
          数据布局: header_num(16B) + marker(3B) + 密文
          解密: AES_CBC_decrypt(key, iv=header_num, data=marker+密文)
          去掉 PKCS#7 填充后得到 UTF-8 正文

        Args:
            data: 加密的正文（不含19字节header）
            header_num: 16位随机数字（作为 IV）
            marker: 3字节标记
            chapter_id: 章节ID
            book_id: 书籍ID

        Returns:
            解密后的字符串
        """
        try:
            from Crypto.Cipher import AES
        except ImportError:
            return ""

        QIMAO_KEY = b"242ccb8230d709e1"

        # IV = header_num 的 ASCII 字节 (16字节)
        iv = header_num.encode('ascii')

        # 密文 = marker + data（补齐到16的倍数）
        ciphertext = marker + data
        if len(ciphertext) % 16 != 0:
            pad_len = 16 - len(ciphertext) % 16
            ciphertext = ciphertext + bytes([pad_len]) * pad_len

        try:
            cipher = AES.new(QIMAO_KEY, AES.MODE_CBC, iv=iv)
            plain = cipher.decrypt(ciphertext)

            # 去掉 PKCS#7 填充
            pad = plain[-1]
            if 1 <= pad <= 16 and plain[-pad:] == bytes([pad]) * pad:
                plain = plain[:-pad]

            return plain.decode('utf-8')
        except Exception:
            return ""

    def _get_content_md5(self, book_id: str, chapter_id: str) -> str:
        """从目录 API 获取章节的 content_md5。"""
        cache_key = f"{book_id}:{chapter_id}"
        if cache_key in self._content_md5_cache:
            return self._content_md5_cache[cache_key]

        try:
            params = _sign_params({"chapter_ver": "0", "id": book_id})
            headers = _make_headers()
            resp = self._http.get(
                "https://api-ks.wtzw.com/api/v1/chapter/chapter-list",
                params=params, headers=headers, timeout=10,
            )
            chapters = resp.json().get("data", {}).get("chapter_lists", [])
            for ch in chapters:
                if ch.get("id") == chapter_id:
                    md5 = ch.get("content_md5", "")
                    self._content_md5_cache[cache_key] = md5
                    return md5
        except Exception:
            pass
        return ""

    # ── 书籍详情 ──────────────────────────────────────────────────────
    def get_book_detail(self, book_id: str) -> dict | None:
        """通过 APP API 获取书籍详细信息。"""
        try:
            params = _sign_params({"id": book_id, "chapter_id": "0"})
            headers = _make_headers()
            resp = self._http.get(
                "https://api-bc.wtzw.com/api/v1/reader/detail",
                params=params, headers=headers, timeout=15,
            )
            if resp.status_code == 200:
                data = resp.json()
                err = data.get("errors", {})
                code = err.get("code", "0")
                if code == "0" or not code:
                    return data.get("data")
        except Exception:
            pass
        return None

    # ── 网页版正文兜底 ──────────────────────────────────────────────
    def _fetch_content_from_web(self, chapter: Chapter) -> str:
        book_id = chapter.book_key.split(":", 1)[1]
        url = chapter.url or f"https://www.qimao.com/shuku/{book_id}-{chapter.chapter_id}/"
        resp = self.session.get(url)
        html = resp.text

        if self._is_vip_locked(html, chapter):
            raise ChapterLockedError(
                "该章节为 VIP 章节，七猫 PC 网页端不提供正文阅读。"
            )

        m = re.search(r'chapterData:\s*"((?:[^"\\]|\\.)*)"', html)
        if not m:
            return ""
        raw = m.group(1)
        if not raw or len(raw) < 20:
            return ""
        try:
            raw = json.loads(f'"{raw}"')
        except json.JSONDecodeError:
            return ""
        if re.match(r"^[A-Za-z0-9+/=_-]{50,}$", raw):
            return ""
        text = re.sub(r"<[^>]+>", "\n", raw)
        text = html_module.unescape(text)
        return re.sub(r"\n{3,}", "\n\n", text).strip()

    def _is_vip_locked(self, html: str, chapter: Chapter) -> bool:
        if chapter.is_vip:
            return True
        if re.search(r'is_vip\s*:\s*(true|e|!0|1)', html):
            return True
        if re.search(r'showDom\s*:\s*[b0]', html):
            return True
        for kw in ["下载【七猫免费小说APP】", "方式一（推荐）", "在APP内免费畅读"]:
            if kw in html:
                return True
        return False

    @staticmethod
    def _clean_text(text: str) -> str:
        text = unescape(text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()


def register_qimao(session: Session, sources: dict) -> str:
    name = "qimao"
    if name not in sources:
        sources[name] = QimaoSource(session)
    return name


__all__ = ["QimaoSource", "register_qimao"]

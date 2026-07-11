"""EPUB 适配器：把 library/ 里的 .epub 当作一本书，spine 里每个文档 = 一章。

只用标准库 zipfile / xml，正文提取复用 parsel。不额外加依赖。
"""
from __future__ import annotations

import glob
import os
import posixpath
import zipfile
from xml.etree import ElementTree as ET

from parsel import Selector

from core.source_base import BaseSource, SourceError
from models import Book, Chapter
import paths

LIBRARY_DIR = paths.library_dir()

CONTAINER = "META-INF/container.xml"


def _ns(tag: str) -> str:
    # 去掉 {namespace} 前缀，方便匹配
    return tag.split("}", 1)[-1]


class _Epub:
    """单个 epub 文件的解析结果：有序的 (标题, 内文档路径) 列表。"""

    def __init__(self, path: str) -> None:
        self.path = path
        self.zip = zipfile.ZipFile(path)
        self.opf_dir, spine = self._parse_opf()
        titles = self._parse_toc()
        self.items: list[tuple[str, str]] = []
        for i, href in enumerate(spine):
            title = titles.get(href) or self._guess_title(href) or f"章节 {i + 1}"
            self.items.append((title, href))

    def _read(self, name: str) -> bytes:
        return self.zip.read(name)

    def _parse_opf(self) -> tuple[str, list[str]]:
        root = ET.fromstring(self._read(CONTAINER))
        opf_path = None
        for el in root.iter():
            if _ns(el.tag) == "rootfile":
                opf_path = el.attrib.get("full-path")
                break
        if not opf_path:
            raise SourceError("epub 缺少 OPF")
        opf_dir = posixpath.dirname(opf_path)

        opf = ET.fromstring(self._read(opf_path))
        id_to_href: dict[str, str] = {}
        spine_ids: list[str] = []
        for el in opf.iter():
            tag = _ns(el.tag)
            if tag == "item":
                id_to_href[el.attrib.get("id", "")] = el.attrib.get("href", "")
            elif tag == "itemref":
                spine_ids.append(el.attrib.get("idref", ""))

        spine = []
        for sid in spine_ids:
            href = id_to_href.get(sid)
            if href:
                spine.append(posixpath.normpath(posixpath.join(opf_dir, href)))
        if not spine:
            raise SourceError("epub spine 为空")
        return opf_dir, spine

    def _parse_toc(self) -> dict[str, str]:
        """尽量从 toc.ncx 取每个文档的标题；失败就返回空。"""
        titles: dict[str, str] = {}
        for name in self.zip.namelist():
            if name.endswith(".ncx"):
                try:
                    ncx = ET.fromstring(self._read(name))
                except ET.ParseError:
                    continue
                ncx_dir = posixpath.dirname(name)
                label = None
                for el in ncx.iter():
                    tag = _ns(el.tag)
                    if tag == "text":
                        label = (el.text or "").strip()
                    elif tag == "content":
                        src = el.attrib.get("src", "").split("#")[0]
                        if src and label:
                            key = posixpath.normpath(posixpath.join(ncx_dir, src))
                            titles.setdefault(key, label)
                break
        return titles

    def _guess_title(self, href: str) -> str:
        try:
            sel = Selector(self._read(href).decode("utf-8", "ignore"))
        except KeyError:
            return ""
        for css in ("h1::text", "h2::text", "title::text"):
            t = sel.css(css).get()
            if t and t.strip():
                return t.strip()
        return ""

    def content(self, index: int) -> str:
        _title, href = self.items[index]
        html = self._read(href).decode("utf-8", "ignore")
        sel = Selector(html)
        parts = sel.css("body ::text").getall()
        text = "\n".join(p.strip() for p in parts if p.strip())
        return text or "（本节无正文）"


class EpubSource(BaseSource):
    name = "epub"

    def __init__(self, session=None) -> None:
        super().__init__(session)
        os.makedirs(LIBRARY_DIR, exist_ok=True)
        self._cache: dict[str, _Epub] = {}

    def _open(self, book_id: str) -> _Epub:
        if book_id not in self._cache:
            self._cache[book_id] = _Epub(os.path.join(LIBRARY_DIR, book_id))
        return self._cache[book_id]

    def search(self, keyword: str) -> list[Book]:
        out = []
        for path in glob.glob(os.path.join(LIBRARY_DIR, "*.epub")):
            fn = os.path.basename(path)
            title = os.path.splitext(fn)[0]
            if not keyword or keyword.lower() in title.lower():
                out.append(Book(source=self.name, book_id=fn, title=title))
        return out

    def get_chapters(self, book: Book) -> list[Chapter]:
        ep = self._open(book.book_id)
        return [
            Chapter(book_key=book.key, index=i, title=t)
            for i, (t, _href) in enumerate(ep.items)
        ]

    def get_content(self, chapter: Chapter) -> str:
        book_id = chapter.book_key.split(":", 1)[1]
        return self._open(book_id).content(chapter.index)

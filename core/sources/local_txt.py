"""本地 txt 适配器：让框架开箱即跑（无需任何网站）。

把 txt 小说放进 novel_reader/library/ 目录，按常见的“第N章”标题自动切分章节。
它是一个完整可用的 BaseSource 参考实现，网站适配器照它的形状写即可。
"""
from __future__ import annotations

import glob
import os
import re

from models import Book, Chapter
from core.source_base import BaseSource
import paths

LIBRARY_DIR = paths.library_dir()

CHAPTER_RE = re.compile(r"^\s*(第\s*[0-9零一二三四五六七八九十百千两]+\s*[章卷回节].*)$")


def _split_chapters(text: str) -> list[tuple[str, str]]:
    lines = text.splitlines()
    chapters: list[tuple[str, list[str]]] = []
    for line in lines:
        if CHAPTER_RE.match(line):
            chapters.append((line.strip(), []))
        elif chapters:
            chapters[-1][1].append(line)
        else:
            chapters.append(("正文", [line]))
    if not chapters:
        chapters = [("全文", lines)]
    return [(t, "\n".join(body).strip()) for t, body in chapters]


class LocalTxtSource(BaseSource):
    name = "local"

    def __init__(self, session=None) -> None:
        super().__init__(session)
        os.makedirs(LIBRARY_DIR, exist_ok=True)
        self._cache: dict[str, list[tuple[str, str]]] = {}

    def _path(self, book_id: str) -> str:
        return os.path.join(LIBRARY_DIR, book_id)

    def _load(self, book_id: str) -> list[tuple[str, str]]:
        if book_id not in self._cache:
            with open(self._path(book_id), encoding="utf-8", errors="ignore") as f:
                self._cache[book_id] = _split_chapters(f.read())
        return self._cache[book_id]

    def search(self, keyword: str) -> list[Book]:
        out = []
        for path in glob.glob(os.path.join(LIBRARY_DIR, "*.txt")):
            fn = os.path.basename(path)
            title = os.path.splitext(fn)[0]
            if not keyword or keyword.lower() in title.lower():
                out.append(Book(source=self.name, book_id=fn, title=title))
        return out

    def get_chapters(self, book: Book) -> list[Chapter]:
        chs = self._load(book.book_id)
        return [
            Chapter(book_key=book.key, index=i, title=t)
            for i, (t, _body) in enumerate(chs)
        ]

    def get_content(self, chapter: Chapter) -> str:
        book_id = chapter.book_key.split(":", 1)[1]
        return self._load(book_id)[chapter.index][1]

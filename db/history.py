"""阅读历史：SQLite 存储。记录每本书读到第几章 + 章节标题 + 滚动进度。"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass

import paths

DB_PATH = paths.db_path()


@dataclass
class HistoryEntry:
    book_key: str
    source: str
    book_title: str
    author: str
    last_index: int
    last_chapter_title: str
    scroll_pos: int
    updated_at: str


class History:
    def __init__(self, path: str = DB_PATH) -> None:
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self._init()

    def _init(self) -> None:
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS history (
                book_key            TEXT PRIMARY KEY,
                source              TEXT,
                book_title          TEXT,
                author              TEXT,
                last_index          INTEGER DEFAULT 0,
                last_chapter_title  TEXT,
                scroll_pos          INTEGER DEFAULT 0,
                updated_at          TEXT DEFAULT (datetime('now','localtime'))
            )
            """
        )
        self.conn.commit()

    def save(self, book_key, source, book_title, author,
             last_index, last_chapter_title, scroll_pos=0) -> None:
        self.conn.execute(
            """
            INSERT INTO history
                (book_key, source, book_title, author,
                 last_index, last_chapter_title, scroll_pos, updated_at)
            VALUES (?,?,?,?,?,?,?, datetime('now','localtime'))
            ON CONFLICT(book_key) DO UPDATE SET
                last_index=excluded.last_index,
                last_chapter_title=excluded.last_chapter_title,
                scroll_pos=excluded.scroll_pos,
                updated_at=excluded.updated_at
            """,
            (book_key, source, book_title, author,
             last_index, last_chapter_title, scroll_pos),
        )
        self.conn.commit()

    def get(self, book_key: str) -> HistoryEntry | None:
        row = self.conn.execute(
            "SELECT * FROM history WHERE book_key=?", (book_key,)
        ).fetchone()
        return self._row(row) if row else None

    def list_recent(self, limit: int = 50) -> list[HistoryEntry]:
        rows = self.conn.execute(
            "SELECT * FROM history ORDER BY updated_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [self._row(r) for r in rows]

    def delete(self, book_key: str) -> None:
        self.conn.execute("DELETE FROM history WHERE book_key=?", (book_key,))
        self.conn.commit()

    def clear(self) -> None:
        """清空全部阅读历史。"""
        self.conn.execute("DELETE FROM history")
        self.conn.commit()

    @staticmethod
    def _row(r: sqlite3.Row) -> HistoryEntry:
        return HistoryEntry(
            book_key=r["book_key"], source=r["source"],
            book_title=r["book_title"], author=r["author"],
            last_index=r["last_index"], last_chapter_title=r["last_chapter_title"],
            scroll_pos=r["scroll_pos"], updated_at=r["updated_at"],
        )

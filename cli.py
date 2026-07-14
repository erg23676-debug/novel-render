"""终端版阅读器入口：python cli.py

纯标准库实现（curses），复用 core / db / sources，无需 PyQt6，可在任意终端运行。
菜单用普通行输入（按书名搜索），阅读用全屏 curses 界面（滚动 + 翻章 + 跳章）。

无 curses（如原生 Windows）时自动降级为简单分屏 pager。
"""
from __future__ import annotations

import sys
import readline  # 启用 readline 行编辑，修复退格删除不完整的问题
import unicodedata
import os
import atexit
import warnings

# 屏蔽 urllib3 在旧版 macOS LibreSSL 上的启动噪音（须在导入 requests 前设置）
warnings.filterwarnings("ignore", message=r".*OpenSSL.*")

from core.session import Session
from core.source_base import ChapterLockedError, SourceError
from core.sources.epub_book import EpubSource
from core.sources.local_txt import LocalTxtSource
from core.sources.website_qimao import register_qimao
from db.history import History
from models import Book

try:
    import curses
except ImportError:  # 原生 Windows 无 curses
    curses = None


# ── 显示宽度感知的换行（中文/全角算 2 列） ──────────────────────────────
def _char_width(ch: str) -> int:
    if ch == "\t":
        return 4
    if unicodedata.east_asian_width(ch) in ("W", "F"):
        return 2
    return 1


def _wrap_line(line: str, width: int) -> list[str]:
    """把一行按可见宽度折成多行；空行原样保留。"""
    if not line.strip():
        return [""]
    out: list[str] = []
    cur, cur_w = "", 0
    for ch in line.rstrip("\n"):
        w = _char_width(ch)
        if cur_w + w > width and cur:
            out.append(cur)
            cur, cur_w = "", 0
        cur += ch
        cur_w += w
    out.append(cur)
    return out


def _render(body: str, width: int, line_gap: int = 0) -> list[str]:
    """把整章正文渲染成一屏宽度内的可见行列表。

    line_gap>0 时在每行之间插入空行，等效于加大行距，减少看错行 / 串行。
    """
    lines: list[str] = []
    for para in body.split("\n"):
        lines.extend(_wrap_line(para, width))
    if line_gap > 0:
        spaced: list[str] = []
        for ln in lines:
            spaced.append(ln)
            spaced.extend([""] * line_gap)
        lines = spaced
    return lines or [""]


def _clip(s: str, width: int) -> str:
    """按可见宽度截断字符串，避免 curses 因宽字符超界报错。"""
    out, w = "", 0
    for ch in s:
        cw = _char_width(ch)
        if w + cw > width:
            break
        out += ch
        w += cw
    return out


def _fit(s: str, width: int) -> str:
    """截断到可见宽度并用空格补齐到 width，使整行高亮背景铺满。"""
    out, w = "", 0
    for ch in s:
        cw = _char_width(ch)
        if w + cw > width:
            break
        out += ch
        w += cw
    return out + " " * (width - w)


class TerminalReader:
    def __init__(self) -> None:
        self.session = Session()
        self.history = History()
        self._line_gap = 1  # 行间空行数（0/1/2），加大可减少看错行
        self.sources: dict[str, object] = {
            "local": LocalTxtSource(),
            "epub": EpubSource(),
        }
        register_qimao(self.session, self.sources)

    # ---------- 主菜单 ----------
    def run(self) -> None:
        # 让 readline 接管输入行编辑，解决退格删除不干净的问题
        histfile = os.path.expanduser("~/.novel_reader_history")
        try:
            readline.read_history_file(histfile)
        except FileNotFoundError:
            pass
        readline.set_history_length(1000)
        atexit.register(readline.write_history_file, histfile)
        readline.parse_and_bind("tab: complete")

        print("📖  小说阅读器 · 终端版")
        print("复用与 GUI 相同的核心 / 历史 / 站点适配器。输入 h 查看帮助。\n")
        while True:
            try:
                cmd = input("reader> ")
            except (EOFError, KeyboardInterrupt):
                print()
                break
            if not cmd:
                continue
            low = cmd.lower()
            if low in ("q", "quit", "exit"):
                break
            elif low in ("h", "help", "?"):
                self._help()
            elif low in ("hist", "history"):
                self.cmd_history()
            elif low in ("lib", "library"):
                self.cmd_library()
            elif low.startswith("s ") or low.startswith("search "):
                self.cmd_search(cmd.split(None, 1)[1].strip())
            else:
                # 不带前缀直接当搜索关键词
                self.cmd_search(cmd)
        print("再见 👋")

    def _help(self) -> None:
        print(
            "命令：\n"
            "  <关键词>            按书名搜索（本地 + 七猫在线）\n"
            "  s <关键词>          同上（显式搜索）\n"
            "  lib                 列出 library/ 里的本地书\n"
            "  hist                打开阅读历史\n"
            "  h                   帮助\n"
            "  q                   退出\n"
            "阅读界面按键：↑/↓ 或 j/k 滚动 · 空格/b 翻页 · n/p 下/上一章 · "
            "t 目录 · g 跳章 · l 行距 · q 返回\n"
        )

    # ---------- 搜索 ----------
    def cmd_search(self, kw: str) -> None:
        if not kw:
            return
        books: list[Book] = []
        errors: list[str] = []

        for n, src in self.sources.items():
            try:
                books.extend(src.search(kw))
            except Exception as e:  # noqa: BLE001
                errors.append(f"{n}: {e}")

        for e in errors:
            print(f"  ⚠ {e}")
        if not books:
            print("（无结果）换个书名，或把 txt/epub 放进 library/ 再搜。")
            return
        self._pick_and_open(books)

    def cmd_library(self) -> None:
        books = self.sources["local"].search("") + self.sources["epub"].search("")
        if not books:
            print("library/ 目录为空。把 .txt / .epub 放进去再试。")
            return
        self._pick_and_open(books)

    def _pick_and_open(self, books: list[Book]) -> None:
        print()
        for i, b in enumerate(books, 1):
            meta = f" · {b.author}" if b.author else ""
            print(f"  [{i:>2}] [{b.source}] {b.title}{meta}")
        book = self._choose(books, "选择书籍编号（回车取消）：")
        if book:
            self.open_book(book)

    # ---------- 历史 ----------
    def cmd_history(self) -> None:
        while True:
            rows = self.history.list_recent()
            if not rows:
                print("暂无阅读历史。")
                return
            print()
            for i, h in enumerate(rows, 1):
                print(f"  [{i:>2}] {h.book_title} · 读到「{h.last_chapter_title}」"
                      f"({h.last_index + 1})  [{h.source}]")
            try:
                raw = input(
                    "编号=继续阅读 · d 编号=删除 · dall=清空 · 回车=返回 > "
                ).strip()
            except (EOFError, KeyboardInterrupt):
                return
            if not raw:
                return

            low = raw.lower()
            if low == "dall":
                self.history.clear()
                print("已清空全部阅读历史。")
                return
            if low.startswith("d"):
                num = raw[1:].strip()
                if num.isdigit() and 1 <= int(num) <= len(rows):
                    h = rows[int(num) - 1]
                    self.history.delete(h.book_key)
                    print(f"已删除「{h.book_title}」的历史。")
                else:
                    print("用法：d <编号>")
                continue

            if raw.isdigit() and 1 <= int(raw) <= len(rows):
                h = rows[int(raw) - 1]
                src = self.sources.get(h.source)
                if not src:
                    print(f"适配器 {h.source} 未注册，请先搜索该源。")
                    continue
                book = Book(source=h.source, book_id=h.book_key.split(":", 1)[1],
                            title=h.book_title, author=h.author)
                self.open_book(book, start_index=h.last_index,
                               top_line=h.scroll_pos)
                return

            print("无效输入。")

    @staticmethod
    def _choose(items: list, prompt: str):
        try:
            raw = input(prompt).strip()
        except (EOFError, KeyboardInterrupt):
            return None
        if not raw.isdigit():
            return None
        idx = int(raw) - 1
        return items[idx] if 0 <= idx < len(items) else None

    # ---------- 打开书 + 目录 ----------
    def open_book(self, book: Book, start_index: int = 0, top_line: int = 0) -> None:
        source = self.sources.get(book.source)
        if not source:
            print(f"适配器 {book.source} 未注册。")
            return
        print(f"加载目录：{book.title} …")
        try:
            chapters = source.get_chapters(book)
        except Exception as e:  # noqa: BLE001
            print(f"目录加载失败：{e}")
            return
        if not chapters:
            print("该书没有章节。")
            return
        # 未指定起点时，从历史续读
        if start_index == 0 and top_line == 0:
            h = self.history.get(book.key)
            if h:
                start_index, top_line = h.last_index, h.scroll_pos

        if curses is None:
            self._read_plain(source, book, chapters, start_index)
        else:
            curses.wrapper(self._read_curses, source, book, chapters,
                           start_index, top_line)

    def _save(self, book: Book, ch, top_line: int) -> None:
        self.history.save(
            book_key=book.key, source=book.source, book_title=book.title,
            author=book.author, last_index=ch.index,
            last_chapter_title=ch.title, scroll_pos=max(0, top_line),
        )

    # ---------- curses 全屏阅读 ----------
    def _read_curses(self, stdscr, source, book, chapters, cur: int,
                     top_line: int) -> None:
        curses.curs_set(0)
        if curses.has_colors():
            curses.use_default_colors()
            curses.init_pair(1, curses.COLOR_WHITE, -1)   # 正文白字
            curses.init_pair(2, curses.COLOR_BLACK, -1)   # 黑字 + 默认背景（用于状态栏）
        stdscr.keypad(True)
        cur = max(0, min(cur, len(chapters) - 1))

        loaded = -1
        lines: list[str] = []
        top = top_line

        while True:
            h, w = stdscr.getmaxyx()
            col = max(20, w - 4)          # 正文列宽（左右各留 2 空）
            page = max(1, h - 3)          # 正文可视行数（头 1 尾 2）

            if loaded != cur:
                ch = chapters[cur]
                try:
                    body = source.get_content(ch)
                except ChapterLockedError as e:
                    body = f"🔒 {ch.title}\n\n{e}\n\n该章节为 VIP，未解锁无法阅读。"
                except SourceError as e:
                    body = f"加载失败：{e}"
                except Exception as e:  # noqa: BLE001
                    body = f"加载失败：{e}"
                lines = _render(body, col, self._line_gap)
                loaded = cur
                self._save(book, ch, top)

            max_top = max(0, len(lines) - page)
            top = max(0, min(top, max_top))

            # —— 绘制
            stdscr.erase()
            ch = chapters[cur]
            head = f" {ch.title}   ({cur + 1}/{len(chapters)})"
            stdscr.addstr(0, 0, _clip(head, w - 1), curses.color_pair(2) | curses.A_BOLD)
            for row in range(page):
                i = top + row
                if i >= len(lines):
                    break
                stdscr.addstr(row + 1, 2, _clip(lines[i], col))
            pct = 100 if len(lines) <= page else int(top / max_top * 100)
            foot = (f" {pct:>3}% │ ↑↓/jk 滚动 · 空格翻页 · n/p 章 · "
                    f"t 目录 · l 行距({self._line_gap}) · q 返回")
            stdscr.addstr(h - 1, 0, _clip(foot, w - 1), curses.color_pair(2) | curses.A_BOLD)
            stdscr.refresh()

            k = stdscr.getch()
            if k in (ord("q"), 27):                       # q / ESC 返回
                self._save(book, ch, top)
                return
            elif k in (curses.KEY_DOWN, ord("j")):
                top = min(max_top, top + 1)
            elif k in (curses.KEY_UP, ord("k")):
                top = max(0, top - 1)
            elif k in (ord(" "), curses.KEY_NPAGE):       # 下一页
                if top >= max_top:
                    if cur < len(chapters) - 1:
                        cur += 1; top = 0
                else:
                    top = min(max_top, top + page)
            elif k in (ord("b"), curses.KEY_PPAGE):       # 上一页
                if top == 0:
                    if cur > 0:
                        cur -= 1; top = 0; loaded = -1  # 载入后置底见下
                        self._save(book, chapters[cur], top)
                else:
                    top = max(0, top - page)
            elif k in (ord("n"), curses.KEY_RIGHT):       # 下一章
                if cur < len(chapters) - 1:
                    cur += 1; top = 0
            elif k in (ord("p"), curses.KEY_LEFT):        # 上一章
                if cur > 0:
                    cur -= 1; top = 0
            elif k == curses.KEY_HOME:
                top = 0
            elif k == curses.KEY_END:
                top = max_top
            elif k == ord("l"):                           # 循环切换行距 0/1/2
                logical = top // (1 + self._line_gap)      # 当前顶行的原始行号
                self._line_gap = (self._line_gap + 1) % 3
                top = logical * (1 + self._line_gap)        # 换算回新行距下的位置
                loaded = -1                                 # 强制按新行距重排
            elif k in (ord("g"), ord("t")):               # 跳章 / 目录
                sel = self._toc_curses(stdscr, chapters, cur)
                if sel is not None:
                    cur = sel; top = 0

    def _toc_curses(self, stdscr, chapters, cur: int):
        """全屏目录选择，返回选中的章节序号或 None。"""
        curses.curs_set(0)
        sel = cur
        while True:
            h, w = stdscr.getmaxyx()
            page = max(1, h - 2)
            top = max(0, min(sel - page // 2, max(0, len(chapters) - page)))
            stdscr.erase()
            stdscr.addstr(0, 0, _clip(" 目录 · ↑↓ 选择 · 回车跳转 · q 返回",
                                      w - 1), curses.color_pair(2) | curses.A_BOLD)
            for row in range(page):
                i = top + row
                if i >= len(chapters):
                    break
                ch = chapters[i]
                mark = "💎 " if ch.is_vip else "   "
                line = f"{i + 1:>4}. {mark}{ch.title}"
                if i == sel:
                    # 反色 + 整行补齐，保证深浅主题下高亮背景都可见且铺满整行
                    stdscr.addstr(row + 1, 1, _fit(line, w - 2),
                                  curses.A_REVERSE | curses.A_BOLD)
                else:
                    stdscr.addstr(row + 1, 1, _clip(line, w - 2), curses.A_NORMAL)
            stdscr.refresh()
            k = stdscr.getch()
            if k in (curses.KEY_DOWN, ord("j")):
                sel = min(len(chapters) - 1, sel + 1)
            elif k in (curses.KEY_UP, ord("k")):
                sel = max(0, sel - 1)
            elif k == curses.KEY_NPAGE:
                sel = min(len(chapters) - 1, sel + page)
            elif k == curses.KEY_PPAGE:
                sel = max(0, sel - page)
            elif k in (curses.KEY_ENTER, 10, 13):
                return sel
            elif k in (ord("q"), 27):
                return None

    # ---------- 无 curses 时的降级 pager ----------
    def _read_plain(self, source, book, chapters, cur: int) -> None:
        while 0 <= cur < len(chapters):
            ch = chapters[cur]
            print(f"\n===== {ch.title}  ({cur + 1}/{len(chapters)}) =====\n")
            try:
                print(source.get_content(ch))
            except (ChapterLockedError, SourceError) as e:
                print(f"[加载失败] {e}")
            self._save(book, ch, 0)
            cmd = input("\n[n]下一章 [p]上一章 [g N]跳章 [q]返回 > ").strip().lower()
            if cmd == "q" or cmd == "":
                return
            elif cmd == "n":
                cur += 1
            elif cmd == "p":
                cur = max(0, cur - 1)
            elif cmd.startswith("g"):
                parts = cmd.split()
                if len(parts) == 2 and parts[1].isdigit():
                    cur = max(0, min(len(chapters) - 1, int(parts[1]) - 1))


def main() -> None:
    TerminalReader().run()


if __name__ == "__main__":
    sys.exit(main())

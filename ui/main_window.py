"""主窗口：左侧（搜索 + 结果 + 历史 + 目录），右侧阅读区。"""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QApplication, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QMenu, QMessageBox, QPushButton, QSplitter, QTabWidget,
    QVBoxLayout, QWidget,
)

from core.session import Session
from core.sources.epub_book import EpubSource
from core.sources.local_txt import LocalTxtSource
from core.sources.website_qimao import register_qimao
from db.history import History
from models import Book
from ui.reader_view import ReaderView
from ui.theme import build_qss


class MainWindow(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("小说阅读器")
        self.resize(1080, 720)

        self.session = Session()
        self.history = History()
        # 已接入的适配器（支持动态注册）
        self.sources: dict[str, object] = {
            "local": LocalTxtSource(),
            "epub": EpubSource(),
        }
        # 自动注册内置网站源
        register_qimao(self.session, self.sources)

        self.cur_source = None
        self.cur_book: Book | None = None
        self.chapters = []
        self._dark = True  # 深色为默认

        # —— 侧栏顶部：搜索框 + 主搜索按钮
        self.search_box = QLineEdit()
        self.search_box.setObjectName("SearchBox")
        self.search_box.setPlaceholderText("🔍  搜索书名（本地 + 七猫在线）…")
        self.search_box.setClearButtonEnabled(True)
        self.search_box.returnPressed.connect(self.do_search)
        search_btn = QPushButton("搜索")
        search_btn.setObjectName("PrimaryBtn")
        search_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        search_btn.clicked.connect(self.do_search)

        search_row = QHBoxLayout()
        search_row.setSpacing(8)
        search_row.addWidget(self.search_box, 1)
        search_row.addWidget(search_btn)

        # —— 图标工具栏：主题
        self.dark_btn = QPushButton("🌙")
        self.dark_btn.setObjectName("IconBtn")
        self.dark_btn.setToolTip("切换日间 / 夜间")
        self.dark_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.dark_btn.clicked.connect(self.toggle_dark)

        tools_row = QHBoxLayout()
        tools_row.setSpacing(4)
        tools_row.addStretch(1)
        tools_row.addWidget(self.dark_btn)

        # —— 侧栏标签页
        self.result_list = QListWidget()
        self.result_list.itemDoubleClicked.connect(self.open_book)

        self.toc_list = QListWidget()
        self.toc_list.itemDoubleClicked.connect(self.jump_chapter)
        self.toc_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.toc_list.customContextMenuRequested.connect(self._toc_context_menu)

        self.hist_list = QListWidget()
        self.hist_list.itemDoubleClicked.connect(self.open_history)

        tabs = QTabWidget()
        tabs.addTab(self.result_list, "搜索结果")
        tabs.addTab(self.toc_list, "目录")
        tabs.addTab(self.hist_list, "历史")
        self.tabs = tabs
        self.tabs.currentChanged.connect(self._on_tab_changed)

        self.sidebar = QWidget()
        self.sidebar.setObjectName("Sidebar")
        self.sidebar.setMinimumWidth(240)
        lv = QVBoxLayout(self.sidebar)
        lv.setContentsMargins(14, 14, 14, 12)
        lv.setSpacing(10)
        lv.addLayout(search_row)
        lv.addLayout(tools_row)
        lv.addWidget(tabs, 1)

        # —— 折叠开关（常驻左侧窄条）
        self.collapse_btn = QPushButton("‹")
        self.collapse_btn.setObjectName("IconBtn")
        self.collapse_btn.setToolTip("折叠 / 展开侧栏")
        self.collapse_btn.setFixedWidth(30)
        self.collapse_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.collapse_btn.clicked.connect(self.toggle_sidebar)
        rail = QWidget()
        rail.setFixedWidth(38)
        rv = QVBoxLayout(rail)
        rv.setContentsMargins(4, 14, 4, 4)
        rv.addWidget(self.collapse_btn)
        rv.addStretch(1)

        # —— 右侧阅读区
        self.reader = ReaderView()
        self.reader.set_theme(self._dark)
        self.reader.progress_changed.connect(self.on_progress)

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.addWidget(self.sidebar)
        self.splitter.addWidget(self.reader)
        self.splitter.setSizes([300, 780])
        self.splitter.setStretchFactor(1, 1)

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(rail)
        root.addWidget(self.splitter, 1)

        self._apply_theme()
        self.refresh_history()

    # ---------- 侧栏折叠 ----------
    def toggle_sidebar(self) -> None:
        visible = not self.sidebar.isVisible()
        self.sidebar.setVisible(visible)
        self.collapse_btn.setText("‹" if visible else "›")

    # ---------- 搜索 ----------
    def do_search(self) -> None:
        kw = self.search_box.text().strip()
        if not kw:
            return

        books: list[Book] = []
        errors = []

        for name, src in self.sources.items():
            try:
                books.extend(src.search(kw))
            except Exception as e:
                errors.append(f"{name}: {e}")

        self.result_list.clear()
        for b in books:
            tag = f"[{b.source}]"
            meta = f"· {b.author}" if b.author else ""
            item = QListWidgetItem(f"{tag} {b.title}  {meta}")
            item.setData(Qt.ItemDataRole.UserRole, b)
            self.result_list.addItem(item)
        self.tabs.setCurrentWidget(self.result_list)

        if not books:
            self.result_list.addItem("（无结果）换个书名，或把 txt / epub 放进 library/ 目录再搜")

        if errors:
            QMessageBox.warning(self, "部分源搜索出错", "\n".join(errors))

    # ---------- 打开书 ----------
    def open_book(self, item: QListWidgetItem, start_index: int = 0,
                  scroll_pos: int = 0) -> None:
        book = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(book, Book):
            return
        self.cur_source = self.sources.get(book.source)
        if not self.cur_source:
            QMessageBox.warning(self, "提示", f"适配器 {book.source} 未注册")
            return
        self.cur_book = book
        try:
            self.chapters = self.cur_source.get_chapters(book)
        except Exception as e:
            QMessageBox.warning(self, "目录加载失败", str(e))
            return
        self._refresh_toc()
        h = self.history.get(book.key)
        if start_index == 0 and h:
            start_index, scroll_pos = h.last_index, h.scroll_pos
        self.reader.load_book(self.cur_source, self.chapters, start_index, scroll_pos)
        self.reader.setFocus()

    def _refresh_toc(self) -> None:
        self.toc_list.clear()
        for ch in self.chapters:
            prefix = "🔒 " if ch.is_vip else "  "
            self.toc_list.addItem(f"{prefix}{ch.title}")
        if self.reader and self.chapters:
            self._highlight_current_toc_item()

    def _highlight_current_toc_item(self) -> None:
        cur = self.reader.cur if self.reader else 0
        if 0 <= cur < self.toc_list.count():
            self.toc_list.item(cur).setSelected(True)
            self.toc_list.scrollToItem(
                self.toc_list.item(cur),
                QListWidget.ScrollHint.PositionAtCenter,
            )

    def _toc_context_menu(self, pos) -> None:
        menu = QMenu(self)
        refresh_action = menu.addAction("🔄 刷新目录")
        jump_action = menu.addAction("📖 跳转到此章节")
        action = menu.exec(self.toc_list.mapToGlobal(pos))
        if action == refresh_action:
            self._reload_toc()
        elif action == jump_action:
            self.jump_chapter(None)

    def _reload_toc(self) -> None:
        if not self.cur_book:
            QMessageBox.warning(self, "提示", "请先打开一本书")
            return
        try:
            self.chapters = self.cur_source.get_chapters(self.cur_book)
        except Exception as e:
            QMessageBox.warning(self, "目录刷新失败", str(e))
            return
        self._refresh_toc()
        QMessageBox.information(self, "已刷新", f"共 {len(self.chapters)} 章")

    def _on_tab_changed(self, index: int) -> None:
        if index == 1 and self.chapters:
            self._highlight_current_toc_item()

    def jump_chapter(self, _item=None) -> None:
        if self.toc_list.currentRow() >= 0:
            self.reader.jump_to(self.toc_list.currentRow())

    # ---------- 历史 ----------
    def on_progress(self, book_key, index, title, scroll_pos) -> None:
        if not self.cur_book:
            return
        self.history.save(
            book_key=book_key, source=self.cur_book.source,
            book_title=self.cur_book.title, author=self.cur_book.author,
            last_index=index, last_chapter_title=title, scroll_pos=scroll_pos,
        )
        self.refresh_history()

    def refresh_history(self) -> None:
        self.hist_list.clear()
        for h in self.history.list_recent():
            item = QListWidgetItem(
                f"{h.book_title}  ·  读到「{h.last_chapter_title}」({h.last_index + 1})"
            )
            item.setData(Qt.ItemDataRole.UserRole, h)
            self.hist_list.addItem(item)

    def open_history(self, item: QListWidgetItem) -> None:
        h = item.data(Qt.ItemDataRole.UserRole)
        src = self.sources.get(h.source)
        if not src:
            QMessageBox.warning(self, "提示", f"适配器 {h.source} 未注册，请先搜索该源")
            return
        self.cur_source = src
        book = Book(source=h.source, book_id=h.book_key.split(":", 1)[1],
                    title=h.book_title, author=h.author)
        fake = QListWidgetItem()
        fake.setData(Qt.ItemDataRole.UserRole, book)
        self.open_book(fake, start_index=h.last_index, scroll_pos=h.scroll_pos)

    # ---------- 主题 ----------
    def _apply_theme(self) -> None:
        QApplication.instance().setStyleSheet(build_qss(self._dark))
        self.dark_btn.setText("☀️" if self._dark else "🌙")
        self.reader.set_theme(self._dark)

    def toggle_dark(self) -> None:
        self._dark = not self._dark
        self._apply_theme()

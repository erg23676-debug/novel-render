"""阅读区：正文显示 + 上一章/下一章 + 字体调节 + 进度记忆。

排版：正文居中限宽（默认最大 760px），阅读级行距与首行缩进，主题感知配色。
"""
from __future__ import annotations

from PyQt6.QtGui import QFont, QTextBlockFormat, QTextCursor
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QHBoxLayout, QLabel, QPushButton, QSpinBox, QTextBrowser,
    QVBoxLayout, QWidget,
)

from core.source_base import ChapterLockedError, SourceError
from models import Chapter
from ui.theme import palette

MAX_COL_WIDTH = 760   # 正文列最大宽度
MIN_MARGIN = 28       # 两侧最小留白


class ReaderView(QWidget):
    # 章节切换时发出（用于外部保存历史）：book_key, index, title, scroll_pos
    progress_changed = pyqtSignal(str, int, str, int)

    def __init__(self) -> None:
        super().__init__()
        self.source = None
        self.chapters: list[Chapter] = []
        self.cur = 0
        self._font_size = 18
        self._dark = True

        # —— 顶部：章节标题 + 进度 + 字号
        self.title_label = QLabel("尚未选择书籍")
        self.title_label.setObjectName("ChapterTitle")
        self.progress_label = QLabel("")
        self.progress_label.setObjectName("ProgressLabel")

        self.font_spin = QSpinBox()
        self.font_spin.setRange(12, 40)
        self.font_spin.setValue(self._font_size)
        self.font_spin.setSuffix(" px")
        self.font_spin.setFixedWidth(74)
        self.font_spin.valueChanged.connect(self._on_font)

        header = QWidget()
        header.setObjectName("ReaderHeader")
        htop = QHBoxLayout(header)
        htop.setContentsMargins(24, 14, 24, 8)
        title_col = QVBoxLayout()
        title_col.setSpacing(2)
        title_col.addWidget(self.title_label)
        title_col.addWidget(self.progress_label)
        htop.addLayout(title_col, 1)
        htop.addWidget(QLabel("字号"))
        htop.addWidget(self.font_spin)

        # —— 正文
        self.text = QTextBrowser()
        self.text.setObjectName("ReaderText")
        self.text.setOpenExternalLinks(False)
        self.text.setFrameShape(QTextBrowser.Shape.NoFrame)

        # —— 底部：翻页 + 计数
        self.prev_btn = QPushButton("← 上一章")
        self.next_btn = QPushButton("下一章 →")
        self.prev_btn.setObjectName("NavBtn")
        self.next_btn.setObjectName("NavBtn")
        self.prev_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.next_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.prev_btn.clicked.connect(self.prev_chapter)
        self.next_btn.clicked.connect(self.next_chapter)
        self.counter_label = QLabel("")
        self.counter_label.setObjectName("ProgressLabel")
        self.counter_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        footer = QWidget()
        footer.setObjectName("ReaderFooter")
        fbot = QHBoxLayout(footer)
        fbot.setContentsMargins(24, 8, 24, 16)
        fbot.addWidget(self.prev_btn)
        fbot.addStretch(1)
        fbot.addWidget(self.counter_label)
        fbot.addStretch(1)
        fbot.addWidget(self.next_btn)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(header)
        layout.addWidget(self.text, 1)
        layout.addWidget(footer)

        self._apply_font()

    # ---------- 排版 ----------
    def _apply_font(self) -> None:
        f = QFont()
        f.setPointSize(self._font_size)
        self.text.setFont(f)
        self._apply_block_format()

    def _apply_block_format(self) -> None:
        """行距 160%、段间距、首行缩进两字符——用块格式实现，避免 Qt CSS 限制。"""
        doc = self.text.document()
        cursor = QTextCursor(doc)
        cursor.select(QTextCursor.SelectionType.Document)
        bf = QTextBlockFormat()
        bf.setLineHeight(
            160, QTextBlockFormat.LineHeightTypes.ProportionalHeight.value
        )
        bf.setTopMargin(4)
        bf.setBottomMargin(10)
        bf.setTextIndent(self._font_size * 2)
        cursor.mergeBlockFormat(bf)

    def _on_font(self, v: int) -> None:
        self._font_size = v
        self._apply_font()

    def _update_margins(self) -> None:
        """让正文列居中限宽。"""
        w = self.text.viewport().width() + self.text.frameWidth() * 2
        side = max(MIN_MARGIN, (self.width() - MAX_COL_WIDTH) // 2)
        self.text.setViewportMargins(side, 18, side, 18)

    def resizeEvent(self, e) -> None:
        super().resizeEvent(e)
        self._update_margins()

    def set_theme(self, dark: bool) -> None:
        self._dark = dark
        if self.chapters:
            self._show(self.text.verticalScrollBar().value())

    # ---------- 加载/翻页 ----------
    def load_book(self, source, chapters: list[Chapter], start_index: int = 0,
                  scroll_pos: int = 0) -> None:
        self.source = source
        self.chapters = chapters
        self.cur = max(0, min(start_index, len(chapters) - 1))
        self._show(scroll_pos)

    def _show(self, scroll_pos: int = 0) -> None:
        if not self.chapters:
            return
        ch = self.chapters[self.cur]
        self.title_label.setText(ch.title)
        total = len(self.chapters)
        self.progress_label.setText(f"第 {self.cur + 1} / {total} 章")
        self.counter_label.setText(f"{self.cur + 1} / {total}")

        c = palette(self._dark)
        try:
            body = self.source.get_content(ch)
            self.text.setPlainText(body)
            self._apply_block_format()
        except ChapterLockedError as e:
            self.text.setHtml(
                f"<div style='color:{c['reading_title']};text-align:center;"
                f"margin-top:60px'>"
                f"<div style='font-size:40px'>🔒</div>"
                f"<h3>{ch.title}</h3>"
                f"<p style='color:#c0693a'>{e}</p>"
                f"<p style='color:{c['muted']}'>请点击工具栏「设置 Cookie」粘贴你已登录"
                f"账号的 Cookie 后重试。程序不会绕过付费。</p></div>"
            )
        except SourceError as e:
            self.text.setHtml(
                f"<p style='color:#c0693a;text-align:center;margin-top:60px'>"
                f"加载失败：{e}</p>"
            )

        self.text.verticalScrollBar().setValue(scroll_pos)
        self.prev_btn.setEnabled(self.cur > 0)
        self.next_btn.setEnabled(self.cur < len(self.chapters) - 1)
        self._update_margins()
        self._emit()

    def _emit(self) -> None:
        if self.chapters:
            ch = self.chapters[self.cur]
            self.progress_changed.emit(
                ch.book_key, self.cur, ch.title,
                self.text.verticalScrollBar().value(),
            )

    def prev_chapter(self) -> None:
        if self.cur > 0:
            self.cur -= 1
            self._show()

    def next_chapter(self) -> None:
        if self.cur < len(self.chapters) - 1:
            self.cur += 1
            self._show()

    def jump_to(self, index: int) -> None:
        if 0 <= index < len(self.chapters):
            self.cur = index
            self._show()

    def keyPressEvent(self, e) -> None:
        if e.key() in (Qt.Key.Key_Left, Qt.Key.Key_PageUp):
            self.prev_chapter()
        elif e.key() in (Qt.Key.Key_Right, Qt.Key.Key_PageDown):
            self.next_chapter()
        else:
            super().keyPressEvent(e)

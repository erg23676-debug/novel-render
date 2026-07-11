"""统一主题：现代扁平风，深色为默认，可切换浅色。

用 objectName 定位控件，主窗口给控件 setObjectName 后由这里的 QSS 上色。
build_qss(dark) 返回整份样式表，palette(dark) 返回阅读区正文用的颜色。
"""
from __future__ import annotations

ACCENT = "#4c8dff"
ACCENT_HOVER = "#5f9bff"
ACCENT_PRESS = "#3f7ae0"

DARK = {
    "window": "#17181c",
    "sidebar": "#1f2126",
    "surface": "#26282e",
    "surface2": "#2d2f36",
    "border": "#34363d",
    "text": "#dce0e6",
    "muted": "#8b909a",
    "sel": "#2f4a7d",
    "reading_bg": "#1c1d21",
    "reading_text": "#c9ccd2",
    "reading_title": "#e8eaee",
}

LIGHT = {
    "window": "#f4f5f7",
    "sidebar": "#ffffff",
    "surface": "#ffffff",
    "surface2": "#eef0f3",
    "border": "#e2e4e8",
    "text": "#2b2d31",
    "muted": "#8a8f98",
    "sel": "#d6e4ff",
    "reading_bg": "#fbfaf7",
    "reading_text": "#33352f",
    "reading_title": "#1d1e20",
}


def palette(dark: bool) -> dict:
    return DARK if dark else LIGHT


def build_qss(dark: bool) -> str:
    c = palette(dark)
    return f"""
    QWidget {{
        background: {c['window']};
        color: {c['text']};
        font-family: -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif;
        font-size: 13px;
    }}

    /* 侧栏容器 */
    #Sidebar {{ background: {c['sidebar']}; border-right: 1px solid {c['border']}; }}
    #SidebarHeader {{ background: transparent; }}

    /* 搜索框 */
    #SearchBox {{
        background: {c['surface']};
        border: 1px solid {c['border']};
        border-radius: 9px;
        padding: 8px 12px;
        selection-background-color: {ACCENT};
    }}
    #SearchBox:focus {{ border: 1px solid {ACCENT}; }}

    /* 主按钮（强调色） */
    #PrimaryBtn {{
        background: {ACCENT}; color: #ffffff;
        border: none; border-radius: 9px;
        padding: 8px 14px; font-weight: 600;
    }}
    #PrimaryBtn:hover {{ background: {ACCENT_HOVER}; }}
    #PrimaryBtn:pressed {{ background: {ACCENT_PRESS}; }}
    #PrimaryBtn:disabled {{ background: {c['surface2']}; color: {c['muted']}; }}

    /* 图标/次级按钮 */
    #IconBtn {{
        background: transparent; color: {c['muted']};
        border: none; border-radius: 8px;
        padding: 6px 8px; font-size: 15px;
    }}
    #IconBtn:hover {{ background: {c['surface2']}; color: {c['text']}; }}
    #IconBtn:checked {{ background: {c['surface2']}; color: {ACCENT}; }}

    /* 标签页 */
    QTabWidget::pane {{ border: none; background: transparent; }}
    QTabBar::tab {{
        background: transparent; color: {c['muted']};
        padding: 7px 12px; margin-right: 2px;
        border: none; border-radius: 7px; font-weight: 500;
    }}
    QTabBar::tab:selected {{ background: {c['surface2']}; color: {c['text']}; }}
    QTabBar::tab:hover:!selected {{ color: {c['text']}; }}

    /* 列表 */
    QListWidget {{
        background: transparent; border: none; outline: none;
        padding: 2px;
    }}
    QListWidget::item {{
        padding: 8px 10px; margin: 1px 2px;
        border-radius: 7px; color: {c['text']};
    }}
    QListWidget::item:hover {{ background: {c['surface2']}; }}
    QListWidget::item:selected {{ background: {c['sel']}; color: {c['text']}; }}

    /* 阅读区 */
    #ReaderText {{
        background: {c['reading_bg']};
        border: none;
        selection-background-color: {ACCENT};
    }}
    #ReaderHeader, #ReaderFooter {{ background: {c['reading_bg']}; }}
    #ChapterTitle {{ color: {c['reading_title']}; font-size: 15px; font-weight: 600; }}
    #ProgressLabel {{ color: {c['muted']}; font-size: 12px; }}

    /* 翻页药丸按钮 */
    #NavBtn {{
        background: {c['surface']}; color: {c['text']};
        border: 1px solid {c['border']}; border-radius: 18px;
        padding: 8px 20px; font-weight: 600;
    }}
    #NavBtn:hover {{ border: 1px solid {ACCENT}; color: {ACCENT}; }}
    #NavBtn:disabled {{ color: {c['muted']}; border-color: {c['border']}; }}

    QSpinBox {{
        background: {c['surface']}; border: 1px solid {c['border']};
        border-radius: 7px; padding: 3px 6px;
    }}

    /* 滚动条 */
    QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
    QScrollBar::handle:vertical {{
        background: {c['border']}; border-radius: 5px; min-height: 30px;
    }}
    QScrollBar::handle:vertical:hover {{ background: {c['muted']}; }}
    QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}

    QMenu {{
        background: {c['surface']}; border: 1px solid {c['border']};
        border-radius: 8px; padding: 4px;
    }}
    QMenu::item {{ padding: 6px 18px; border-radius: 6px; }}
    QMenu::item:selected {{ background: {c['surface2']}; }}
    """

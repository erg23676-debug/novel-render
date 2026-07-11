# 小说阅读器（桌面 GUI）

Python + PyQt6 的桌面小说阅读器。
支持**本地 txt / epub 阅读**和**在线搜索阅读七猫小说**，带阅读历史（记住读到第几章 + 滚动进度）、
字体调节、夜间模式。

GUI 与终端版共用同一套核心，可无缝续读。

## 运行

```bash
cd novel_reader
python3 -m pip install -r requirements.txt

python3 main.py           # 桌面 GUI（PyQt6）
python3 main.py --tui     # 终端版（纯标准库 curses，无需 PyQt6）
python3 cli.py            # 终端版（等价入口）
```

开箱即用的是**本地源**：把 `.txt` / `.epub` 小说放进 `library/` 目录，程序自动切分章节。
在线部分内置**七猫**：搜索框输入书名即可跨本地 + 七猫聚合搜索。

### 终端版操作

- 主菜单：输入书名关键词搜索；`lib` 列本地书，`hist` 打开历史，`h` 帮助，`q` 退出。
- 阅读界面：`↑/↓` 或 `j/k` 滚动 · 空格/`b` 翻页 · `n/p` 下/上一章 · `t` 或 `g` 目录跳章 · `q` 返回。
- 中文/全角字符按 2 列宽度正确折行；无 `curses` 的环境自动降级为简单分屏。

## 目录结构

```
novel_reader/
├── main.py                      # 入口（GUI，--tui 转终端版）
├── cli.py                       # 终端版（curses TUI，复用同一套核心）
├── models.py                    # Book / Chapter 数据模型
├── paths.py                     # 数据目录解析（源码目录 / 打包后用户目录）
├── core/
│   ├── session.py               # 网络会话
│   ├── source_base.py           # 适配器基类
│   └── sources/
│       ├── local_txt.py         # 本地 txt 源
│       ├── epub_book.py         # 本地 epub 源
│       └── website_qimao.py     # 七猫在线源
├── db/history.py                # SQLite 阅读历史
├── ui/                          # PyQt6 界面
├── library/                     # 放本地 txt / epub
└── packaging/                   # 打包脚本（生成双击安装的 .pkg）
```

## 主要功能

### 🔍 搜索
在搜索框输入**书名关键词**，跨本地书库和七猫在线聚合搜索。

### 📚 完整章节目录
- 左侧「目录」标签页展示完整章节目录，右键可「刷新目录」「跳转到此章节」
- 历史记录保留阅读进度（章节 + 滚动位置）

### 📖 阅读体验
- 上一章/下一章（支持 ← → 方向键和 PageUp/PageDown）
- 字体大小调节 · 章节进度自动保存 · 夜间模式切换

## 关于 VIP 章节

七猫的 VIP 章节未解锁时，适配器 `raise ChapterLockedError`，界面提示为 VIP 无法阅读。
**本项目不包含任何解密、逆向、绕过付费墙的逻辑。**

## 打包分发

见 `packaging/README.md`：一条命令生成 macOS 双击安装的 `.pkg`，装完后
「应用程序」里出现「小说阅读器」，终端也能直接 `novel` 使用。

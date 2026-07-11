# 小说阅读器（桌面 GUI）

Python + PyQt6 的桌面小说阅读器。
支持搜索、上一章/下一章、阅读历史（记住读到第几章 + 滚动进度）、字体调节、夜间模式、
本地 txt / epub 导入、**URL 自动注册网站源**、**canvas 反爬章节提取**。

多站点通过"适配器"接入，搜索跨所有源聚合。

## 运行

```bash
cd novel_reader
python3 -m pip install -r requirements.txt

python3 main.py          # 桌面 GUI（PyQt6）
python3 main.py --tui     # 终端版（纯标准库 curses，无需 PyQt6）
python3 cli.py            # 终端版（等价入口）
```

GUI 与终端版**共用同一套核心**（`models` / `core` / `db` / `sources`）和阅读历史，
可以在两边之间无缝续读。

开箱即用的是**本地 txt 源**：把 `.txt` 小说放进 `library/` 目录，程序按"第N章"自动切分章节。

### 终端版操作

- 主菜单：输入书名关键词或粘贴小说 URL 直接搜索；`lib` 列本地书，`hist` 打开历史，
  `cookie` 设置登录态，`h` 帮助，`q` 退出。
- 阅读界面：`↑/↓` 或 `j/k` 滚动 · 空格/`b` 翻页 · `n/p` 下/上一章 · `t` 或 `g` 目录跳章 · `q` 返回。
- 中文/全角字符按 2 列宽度正确折行；无 `curses` 的环境（如原生 Windows）自动降级为简单分屏。

## 目录结构

```
novel_reader/
├── main.py                      # 入口（GUI，--tui 转终端版）
├── cli.py                       # 终端版（curses TUI，复用同一套核心）
├── models.py                    # Book / Chapter 数据模型
├── core/
│   ├── session.py               # 网络会话 + Cookie（合法登录态）
│   ├── source_base.py           # 适配器基类 + DynamicWebsiteSource
│   └── sources/
│       ├── local_txt.py         # 本地 txt 源（完整参考实现）
│       ├── epub_book.py         # 本地 epub 源（zipfile 解析）
│       ├── website_template.py  # 网站适配器模板（照它填三个方法）
│       ├── website_dynamic.py   # 通用动态网站源（输入 URL 自动适配）
│       └── canvas_decoder.py    # Canvas 反爬章节文字提取模块
├── db/history.py                # SQLite 阅读历史
├── ui/                          # PyQt6 界面
└── library/                     # 放本地 txt
```

## 主要功能

### 🔍 搜索
- 在搜索框输入**书名关键词**：跨所有已注册源搜索
- 在搜索框输入**小说 URL**：自动注册对应网站源，解析书籍信息和目录
  - 例如输入 `https://www.example.com/book/12345` 即可解析

### 📚 完整章节目录
- 左侧"目录"标签页展示完整章节目录
- 右键菜单支持「刷新目录」和「跳转到此章节」
- 切换标签页到目录时自动高亮当前章节
- 历史记录保留阅读进度（章节 + 滚动位置）

### 🎨 Canvas 反爬处理
某些网站用 `qm-canvas-txt` 画布渲染做反爬，本程序支持：
- **隐藏备份提取**：检测 `<noscript>` / `display:none` / `aria-hidden` 中的备份文本
- **Script 数据探测**：从 `window.__DATA__` / `__NUXT__` / `__INITIAL_STATE__` 等 JS 变量中提取
- **JSON-LD 提取**：从结构化数据中提取正文
- **Playwright 浏览器渲染**（可选）：安装 `playwright` 后可使用无头浏览器渲染 canvas

### 📖 阅读体验
- 上一章/下一章（支持 ← → 方向键和 PageUp/PageDown）
- 字体大小调节
- 章节进度自动保存
- 夜间模式切换

## 接入一个网站

### 方式一：自动适配（推荐）
直接在搜索框粘贴小说详情页 URL，程序自动解析。适合大多数小说网站。

### 方式二：手动适配
复制 `website_template.py`，把 `BASE` 改成域名，填好三个方法，在 `main_window.py` 注册。

## 关于 VIP 章节（重要）

本项目**只支持合法登录态**：你用自己的账号在浏览器登录后，点"设置 Cookie"把 Cookie 粘进来，
程序带着这份登录态去请求你**已购买/已解锁**的章节。

- 未解锁的 VIP 章节 → 适配器 `raise ChapterLockedError`，界面提示去登录/购买。
- **本项目不包含、也不会加入任何解密、逆向、绕过付费墙的逻辑。** 这是设计上的硬边界。

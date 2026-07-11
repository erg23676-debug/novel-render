# 打包与分发（macOS）

把项目打成一个**双击即装**的 `.pkg`。装完之后：

- **应用程序**里出现「小说阅读器」，双击打开图形界面；
- 终端里直接输入 **`novel`** 进终端版，`novel --gui` 开图形界面。

用户无需安装 Python、无需下载源代码、无需 `pip install`——Python 和所有依赖都打进包里了。

## 重新构建

```bash
bash packaging/build.sh
```

产物在 `packaging/dist/`：

- `小说阅读器.app` —— 独立应用（可直接拖进「应用程序」）
- `小说阅读器-安装包.pkg` —— 分发用的安装包（就发这个文件）

首次运行会自动 `pip install --user pyinstaller`。需要 `pkgbuild`（macOS 自带）。

## 安装（发给别人）

把 `小说阅读器-安装包.pkg` 发给对方，双击安装即可。

> **Gatekeeper 提示**：这个包是 ad-hoc 签名、未做 Apple 公证。首次双击若提示
> “无法打开，来自身份不明的开发者”，让对方**右键点 `.pkg` → 打开**，再点“打开”即可；
> 或到「系统设置 → 隐私与安全性」点“仍要打开”。做正式对外分发才需要 Apple 开发者证书公证。

## 数据存放

打包版把阅读历史和书库写到用户目录，**不写进 app 内部**（app 是只读的）：

```
~/Library/Application Support/小说阅读器/
├── reader.db        # 阅读历史
└── library/         # 放本地 txt / epub
```

源码方式运行时仍写在项目目录（行为不变）。可用环境变量 `NOVEL_READER_HOME` 覆盖数据目录。

## 原理

- `paths.py` 统一解析数据目录：源码运行→项目目录；打包运行（`sys.frozen`）→ 用户目录。
- `build.sh`：PyInstaller `--windowed` 生成 `.app`（同一个可执行文件既是 GUI 又能 `--tui` 跑终端版），
  再把 `.app` + `novel` 包装脚本组装进 `pkgroot/`，用 `pkgbuild` 打成 `.pkg`。
- `novel`：安装到 `/usr/local/bin` 的包装脚本，转调 app 内的可执行文件。

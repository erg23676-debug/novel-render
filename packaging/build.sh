#!/bin/bash
# 一键打包：PyInstaller 生成 小说阅读器.app，再用 pkgbuild 打成双击安装的 .pkg。
# 安装后：/Applications/小说阅读器.app（双击开图形界面）+ /usr/local/bin/novel（终端命令）。
#
# 用法：  bash packaging/build.sh
# 产物：  packaging/dist/小说阅读器-安装包.pkg
set -euo pipefail

# ---- 路径 ----
HERE="$(cd -P "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd -P "$HERE/.." && pwd)"
BUILD="$HERE/build"          # PyInstaller 中间产物
DIST="$HERE/dist"            # 最终 .app / .pkg
PKGROOT="$HERE/pkgroot"      # 组装安装负载
APP_NAME="小说阅读器"
BUNDLE_ID="com.novelreader.app"
VERSION="1.0.0"
PY="${PYTHON:-python3}"

echo "==> 项目根目录: $ROOT"

# ---- 1. 确保 PyInstaller 就绪 ----
if ! "$PY" -c "import PyInstaller" >/dev/null 2>&1; then
  echo "==> 安装 PyInstaller ..."
  "$PY" -m pip install --user pyinstaller
fi

# ---- 2. 清理旧产物 ----
rm -rf "$BUILD" "$DIST" "$PKGROOT" "$HERE"/*.spec
mkdir -p "$DIST"

# ---- 3. PyInstaller 构建 .app ----
echo "==> PyInstaller 构建 $APP_NAME.app ..."
"$PY" -m PyInstaller \
  --noconfirm --clean --windowed \
  --name "$APP_NAME" \
  --osx-bundle-identifier "$BUNDLE_ID" \
  --distpath "$DIST" \
  --workpath "$BUILD" \
  --specpath "$HERE" \
  --paths "$ROOT" \
  --hidden-import cli \
  --hidden-import paths \
  --hidden-import core.sources.local_txt \
  --hidden-import core.sources.epub_book \
  --hidden-import core.sources.website_dynamic \
  --hidden-import core.sources.website_qimao \
  --hidden-import core.sources.website_template \
  --hidden-import core.sources.canvas_decoder \
  "$ROOT/main.py"

APP_PATH="$DIST/$APP_NAME.app"
[ -d "$APP_PATH" ] || { echo "构建失败：找不到 $APP_PATH" >&2; exit 1; }

# ad-hoc 签名，减少 Gatekeeper 干扰（非公证，仅本机/内部分发够用）
echo "==> ad-hoc 代码签名 ..."
codesign --force --deep --sign - "$APP_PATH" >/dev/null 2>&1 || \
  echo "   (codesign 跳过，不影响使用)"

# ---- 4. 组装安装负载 ----
echo "==> 组装安装负载 ..."
mkdir -p "$PKGROOT/Applications"
mkdir -p "$PKGROOT/usr/local/bin"
cp -R "$APP_PATH" "$PKGROOT/Applications/"
cp "$HERE/novel" "$PKGROOT/usr/local/bin/novel"
chmod 755 "$PKGROOT/usr/local/bin/novel"

# ---- 5. 打成 .pkg ----
echo "==> 生成 .pkg ..."
PKG_OUT="$DIST/$APP_NAME-安装包.pkg"
pkgbuild \
  --root "$PKGROOT" \
  --identifier "$BUNDLE_ID.installer" \
  --version "$VERSION" \
  --install-location "/" \
  "$PKG_OUT"

echo ""
echo "======================================================"
echo " 完成！安装包："
echo "   $PKG_OUT"
echo ""
echo " 双击它安装后："
echo "   · 应用程序里出现「${APP_NAME}」，双击打开图形界面"
echo "   · 终端直接输入  novel        进终端版"
echo "   · 终端输入      novel --gui   开图形界面"
echo "======================================================"

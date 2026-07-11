"""数据目录解析。

源码运行时：数据放在项目目录（`reader.db` / `library/`），保持原来的开发体验。
打包成 .app 后：app 内部是只读的，改把数据写到用户目录
`~/Library/Application Support/小说阅读器/`，避免一保存历史就崩。

可用环境变量 `NOVEL_READER_HOME` 强制指定数据目录（测试 / 便携用途）。
"""
from __future__ import annotations

import os
import sys

_APP_NAME = "小说阅读器"


def data_dir() -> str:
    """返回可写的数据根目录，并确保存在。"""
    override = os.environ.get("NOVEL_READER_HOME")
    if override:
        base = os.path.expanduser(override)
    elif getattr(sys, "frozen", False):
        # PyInstaller 打包后：写到用户的 Application Support
        base = os.path.expanduser(
            os.path.join("~/Library/Application Support", _APP_NAME)
        )
    else:
        # 源码运行：项目根目录（本文件所在目录），与旧行为一致
        base = os.path.dirname(os.path.abspath(__file__))
    os.makedirs(base, exist_ok=True)
    return base


def db_path() -> str:
    """reader.db 的完整路径。"""
    return os.path.join(data_dir(), "reader.db")


def library_dir() -> str:
    """本地 txt / epub 书库目录，并确保存在。"""
    d = os.path.join(data_dir(), "library")
    os.makedirs(d, exist_ok=True)
    return d

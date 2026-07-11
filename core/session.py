"""网络会话：统一的 requests 会话 + 默认请求头。"""
from __future__ import annotations

import requests

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0 Safari/537.36"
    ),
}


class Session:
    def __init__(self) -> None:
        self._s = requests.Session()
        self._s.headers.update(DEFAULT_HEADERS)

    def get(self, url: str, **kw) -> requests.Response:
        kw.setdefault("timeout", 15)
        return self._s.get(url, **kw)

    def post(self, url: str, **kw) -> requests.Response:
        kw.setdefault("timeout", 15)
        return self._s.post(url, **kw)

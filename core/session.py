"""网络会话 + Cookie 管理。

VIP/付费章节的合法读取路径：用户在浏览器登录自己的账号后，把 Cookie 粘贴进来，
程序带着这份登录态去请求。程序本身不做任何解密/绕过。
"""
from __future__ import annotations

import http.cookies

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

    def set_cookie_string(self, cookie_str: str) -> None:
        """粘贴浏览器里的 Cookie 字符串（形如 'a=1; b=2'），作为登录态。"""
        jar = http.cookies.SimpleCookie()
        jar.load(cookie_str)
        for k, morsel in jar.items():
            self._s.cookies.set(k, morsel.value)

    def clear_cookies(self) -> None:
        self._s.cookies.clear()

    def get(self, url: str, **kw) -> requests.Response:
        kw.setdefault("timeout", 15)
        return self._s.get(url, **kw)

    def post(self, url: str, **kw) -> requests.Response:
        kw.setdefault("timeout", 15)
        return self._s.post(url, **kw)

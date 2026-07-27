"""共用测试替身：脚本化的 urlopen 替代品，单元测试永不碰真实网络。"""
from __future__ import annotations

import io
import json
import urllib.error
from typing import Any, Dict, List, Optional, Tuple


class FakeResponse:
    def __init__(self, status: int = 200, body: Any = None, headers: Optional[Dict[str, str]] = None):
        self.status = status
        self._body = body if isinstance(body, (str, bytes)) else json.dumps(body or {})
        self.headers = headers or {}

    def read(self) -> bytes:
        return self._body.encode("utf-8") if isinstance(self._body, str) else self._body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class FakeOpener:
    """script: 依次弹出的结果列表。元素可为 FakeResponse、Exception 实例。
    记录每次请求的 (url, headers) 供断言。"""

    def __init__(self, script: List[Any]):
        self.script = list(script)
        self.calls: List[Tuple[str, Dict[str, str]]] = []

    def __call__(self, req, timeout=None):
        url = req.full_url if hasattr(req, "full_url") else str(req)
        headers = dict(getattr(req, "headers", {}) or {})
        self.calls.append((url, headers))
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def http_error(url: str, code: int, headers: Optional[Dict[str, str]] = None) -> urllib.error.HTTPError:
    import email.message
    msg = email.message.Message()
    for k, v in (headers or {}).items():
        msg[k] = v
    return urllib.error.HTTPError(url, code, f"HTTP {code}", msg, io.BytesIO(b"{}"))

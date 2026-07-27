"""HTTP 层：唯一接触网络的模块。节流、指数退避（全抖动）、错误分类。

spec·第 5 节组件 1、第 8 节退避参数、第 9 节错误码。
"""
from __future__ import annotations

import json
import random
import socket
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Callable, Dict, Optional


class TransportError(Exception):
    """网络/服务故障，code ∈ models.ERROR_CODES。"""

    def __init__(self, code: str, detail: str = "", retry_after: Optional[float] = None):
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail
        self.retry_after = retry_after   # 仅 RATE_LIMITED 由 Retry-After 头填充


class NotFoundError(Exception):
    """HTTP 404——对 lookup 语义是 miss（查了没有），不是故障。"""


class Throttle:
    """每源一个：保证相邻请求间隔 ≥ min_interval_s。

    批处理引擎的通用 worker 池可能并发访问同一源的 Throttle，
    故 wait() 用锁串行化——持锁期间 sleep 使同源请求自然排队。
    """

    def __init__(self, min_interval_s: float,
                 clock: Callable[[], float] = time.monotonic,
                 sleep: Callable[[float], None] = time.sleep):
        self.min_interval_s = min_interval_s
        self._clock = clock
        self._sleep = sleep
        self._last: Optional[float] = None
        self._lock = threading.Lock()

    def wait(self) -> None:
        with self._lock:
            now = self._clock()
            if self._last is not None:
                remaining = self.min_interval_s - (now - self._last)
                if remaining > 0:
                    self._sleep(remaining)
            self._last = self._clock()


@dataclass
class RetryPolicy:
    base: float = 1.0
    factor: float = 2.0
    max_delay: float = 60.0
    max_attempts: int = 5


class Transport:
    def __init__(self, user_agent: str, mailto: Optional[str] = None,
                 timeout: float = 30.0, retry: Optional[RetryPolicy] = None,
                 sleep: Callable[[float], None] = time.sleep,
                 rand: Callable[[], float] = random.random,
                 opener: Optional[Callable] = None):
        self.user_agent = f"{user_agent} (mailto:{mailto})" if mailto else user_agent
        self.timeout = timeout
        self.retry = retry or RetryPolicy()
        self.sleep = sleep   # 公开：build_clients 复用它构造每源 Throttle，
                             # 使限流 sleep 与退避 sleep 共享同一注入点（测试可整链 no-op）
        self._rand = rand
        self._opener = opener or urllib.request.urlopen

    # ---- 公共入口 ----

    def get_json(self, url: str, headers: Optional[Dict[str, str]] = None,
                 throttle: Optional[Throttle] = None) -> dict:
        text = self.get_text(url, headers=headers, throttle=throttle)
        try:
            return json.loads(text)
        except ValueError as e:
            raise TransportError("PARSE_ERROR", f"{url}: {e}")

    def get_text(self, url: str, headers: Optional[Dict[str, str]] = None,
                 throttle: Optional[Throttle] = None) -> str:
        attempt = 0
        while True:
            attempt += 1
            if throttle is not None:
                throttle.wait()
            try:
                return self._once(url, headers or {})
            except NotFoundError:
                raise
            except TransportError as e:
                if attempt >= self.retry.max_attempts:
                    raise
                self.sleep(self._delay(attempt, e.retry_after))

    # ---- 内部 ----

    def _once(self, url: str, headers: Dict[str, str]) -> str:
        req = urllib.request.Request(url)
        req.add_header("User-Agent", self.user_agent)
        req.add_header("Accept", "application/json, application/atom+xml;q=0.9, */*;q=0.8")
        for k, v in headers.items():
            req.add_header(k, v)
        try:
            with self._opener(req, timeout=self.timeout) as resp:
                return resp.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            if e.code == 404:
                raise NotFoundError(url)
            if e.code == 429:
                ra = e.headers.get("Retry-After") if e.headers else None
                retry_after = None
                if ra is not None:
                    try:
                        retry_after = float(ra)
                    except ValueError:
                        pass
                raise TransportError("RATE_LIMITED", f"{url}: HTTP 429", retry_after=retry_after)
            # 404/429 已在上方处理；其余状态码统一归 SERVER_ERROR
            raise TransportError("SERVER_ERROR", f"{url}: HTTP {e.code}")
        except socket.timeout:
            raise TransportError("TIMEOUT", url)
        except urllib.error.URLError as e:
            reason = getattr(e, "reason", None)
            if isinstance(reason, socket.timeout):
                raise TransportError("TIMEOUT", url)
            if isinstance(reason, socket.gaierror):
                raise TransportError("DNS_FAIL", f"{url}: {reason}")
            raise TransportError("CONN_FAILED", f"{url}: {reason}")
        except (ConnectionError, OSError) as e:
            raise TransportError("CONN_FAILED", f"{url}: {e}")

    def _delay(self, attempt: int, retry_after: Optional[float]) -> float:
        if retry_after is not None:
            return retry_after
        raw = min(self.retry.max_delay, self.retry.base * (self.retry.factor ** (attempt - 1)))
        return raw * self._rand()   # 全抖动（full jitter）

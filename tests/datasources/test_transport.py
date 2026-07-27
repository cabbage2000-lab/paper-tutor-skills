from __future__ import annotations

import socket
import unittest
import urllib.error

from paper_shared.datasources.transport import (NotFoundError, RetryPolicy, Throttle,
                                              Transport, TransportError)
from tests.datasources.fakes import FakeOpener, FakeResponse, http_error


class FakeClock:
    def __init__(self):
        self.now = 0.0
        self.sleeps = []

    def monotonic(self):
        return self.now

    def sleep(self, s):
        self.sleeps.append(s)
        self.now += s


class TestThrottle(unittest.TestCase):
    def test_enforces_min_interval(self):
        clk = FakeClock()
        th = Throttle(3.0, clock=clk.monotonic, sleep=clk.sleep)
        th.wait()                       # 首次不等
        self.assertEqual(clk.sleeps, [])
        clk.now += 1.0
        th.wait()                       # 距上次 1s，需再等 2s
        self.assertEqual(clk.sleeps, [2.0])


class TestTransport(unittest.TestCase):
    def _t(self, script, **kw):
        clk = FakeClock()
        opener = FakeOpener(script)
        t = Transport(user_agent="Paper-test/0", opener=opener,
                      sleep=clk.sleep, rand=lambda: 1.0, **kw)
        return t, opener, clk

    def test_get_json_ok_and_ua_header(self):
        t, opener, _ = self._t([FakeResponse(200, {"ok": 1})])
        self.assertEqual(t.get_json("https://x/api"), {"ok": 1})
        url, headers = opener.calls[0]
        self.assertIn("Paper-test/0", headers.get("User-agent", headers.get("User-Agent", "")))

    def test_mailto_appended_to_ua(self):
        t = Transport(user_agent="Paper-test/0", mailto="a@b.c",
                      opener=FakeOpener([FakeResponse(200, {})]))
        self.assertIn("mailto:a@b.c", t.user_agent)

    def test_404_raises_notfound_no_retry(self):
        t, opener, _ = self._t([http_error("https://x", 404)])
        with self.assertRaises(NotFoundError):
            t.get_json("https://x")
        self.assertEqual(len(opener.calls), 1)

    def test_429_retries_with_retry_after(self):
        t, opener, clk = self._t(
            [http_error("https://x", 429, {"Retry-After": "7"}), FakeResponse(200, {"ok": 1})])
        self.assertEqual(t.get_json("https://x"), {"ok": 1})
        self.assertEqual(clk.sleeps, [7.0])   # 尊重 Retry-After 而非退避公式

    def test_5xx_exponential_backoff_then_error(self):
        t, opener, clk = self._t(
            [http_error("https://x", 500)] * 5,
            retry=RetryPolicy(base=1.0, factor=2.0, max_delay=60.0, max_attempts=5))
        with self.assertRaises(TransportError) as ctx:
            t.get_json("https://x")
        self.assertEqual(ctx.exception.code, "SERVER_ERROR")
        self.assertEqual(clk.sleeps, [1.0, 2.0, 4.0, 8.0])   # rand=1.0 → 全额退避

    def test_timeout_classified(self):
        t, _, _ = self._t([socket.timeout()] * 5)
        with self.assertRaises(TransportError) as ctx:
            t.get_json("https://x")
        self.assertEqual(ctx.exception.code, "TIMEOUT")

    def test_dns_fail_classified(self):
        err = urllib.error.URLError(socket.gaierror(8, "nodename nor servname provided"))
        t, _, _ = self._t([err] * 5)
        with self.assertRaises(TransportError) as ctx:
            t.get_json("https://x")
        self.assertEqual(ctx.exception.code, "DNS_FAIL")

    def test_bad_json_is_parse_error(self):
        t, _, _ = self._t([FakeResponse(200, "not json{{")])
        with self.assertRaises(TransportError) as ctx:
            t.get_json("https://x")
        self.assertEqual(ctx.exception.code, "PARSE_ERROR")


if __name__ == "__main__":
    unittest.main()

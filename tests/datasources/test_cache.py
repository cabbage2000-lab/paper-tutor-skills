from __future__ import annotations

import os
import pathlib
import tempfile
import unittest
from unittest import mock

from paper_shared.datasources.cache import Cache, default_cache_dir


class TestDefaultCacheDir(unittest.TestCase):
    def test_env_priority(self):
        with mock.patch.dict(os.environ, {"PAPER_CACHE_DIR": "/tmp/paper-x",
                                          "XDG_CACHE_HOME": "/tmp/xdg"}):
            self.assertEqual(default_cache_dir(), pathlib.Path("/tmp/paper-x"))
        with mock.patch.dict(os.environ, {"XDG_CACHE_HOME": "/tmp/xdg"}, clear=False):
            os.environ.pop("PAPER_CACHE_DIR", None)
            self.assertEqual(default_cache_dir(), pathlib.Path("/tmp/xdg/paper"))

    def test_home_fallback(self):
        env = {k: v for k, v in os.environ.items()
               if k not in ("PAPER_CACHE_DIR", "XDG_CACHE_HOME")}
        with mock.patch.dict(os.environ, env, clear=True):
            self.assertEqual(default_cache_dir(), pathlib.Path.home() / ".cache" / "paper")


class TestCache(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cache = Cache(pathlib.Path(self.tmp.name) / "t.db")

    def tearDown(self):
        self.tmp.cleanup()

    def test_miss_returns_none(self):
        self.assertIsNone(self.cache.get("crossref", "doi:x", ttl_days=7))

    def test_put_get_roundtrip(self):
        self.cache.put("crossref", "doi:x", {"a": 1}, now=1000.0)
        self.assertEqual(self.cache.get("crossref", "doi:x", ttl_days=7, now=1000.0), {"a": 1})

    def test_ttl_expiry(self):
        self.cache.put("crossref", "doi:x", {"a": 1}, now=0.0)
        eight_days = 8 * 86400.0
        self.assertIsNone(self.cache.get("crossref", "doi:x", ttl_days=7, now=eight_days))
        self.assertEqual(self.cache.get("crossref", "doi:x", ttl_days=30, now=eight_days), {"a": 1})

    def test_put_overwrites(self):
        self.cache.put("s", "k", {"v": 1}, now=0.0)
        self.cache.put("s", "k", {"v": 2}, now=1.0)
        self.assertEqual(self.cache.get("s", "k", ttl_days=7, now=2.0), {"v": 2})


if __name__ == "__main__":
    unittest.main()

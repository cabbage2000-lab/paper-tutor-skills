"""本地响应缓存：性能设施而非证据（spec·第 8 节）。

sqlite3 单文件；每次操作独立连接（sqlite3 连接不可跨线程共享，
批处理引擎多 worker 并发访问时以短连接换安全，本地文件性能足够）。
"""
from __future__ import annotations

import json
import os
import pathlib
import sqlite3
import time
from typing import Any, Dict, Optional

_SCHEMA = """
CREATE TABLE IF NOT EXISTS cache (
  source     TEXT NOT NULL,
  key        TEXT NOT NULL,
  payload    TEXT NOT NULL,
  fetched_at REAL NOT NULL,
  PRIMARY KEY (source, key)
)
"""


def default_cache_dir() -> pathlib.Path:
    env = os.environ.get("PAPER_CACHE_DIR")
    if env:
        return pathlib.Path(env)
    xdg = os.environ.get("XDG_CACHE_HOME")
    if xdg:
        return pathlib.Path(xdg) / "paper"
    return pathlib.Path.home() / ".cache" / "paper"


class Cache:
    def __init__(self, db_path: Optional[pathlib.Path] = None):
        self.db_path = pathlib.Path(db_path) if db_path else default_cache_dir() / "datasources.db"
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as c:
            c.execute(_SCHEMA)

    def _conn(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path, timeout=10.0)

    def get(self, source: str, key: str, ttl_days: float,
            now: Optional[float] = None) -> Optional[Dict[str, Any]]:
        now = time.time() if now is None else now
        with self._conn() as c:
            row = c.execute("SELECT payload, fetched_at FROM cache WHERE source=? AND key=?",
                            (source, key)).fetchone()
        if row is None:
            return None
        payload, fetched_at = row
        if now - fetched_at > ttl_days * 86400.0:
            return None
        return json.loads(payload)

    def put(self, source: str, key: str, payload: Dict[str, Any],
            now: Optional[float] = None) -> None:
        now = time.time() if now is None else now
        with self._conn() as c:
            c.execute("INSERT OR REPLACE INTO cache (source, key, payload, fetched_at) "
                      "VALUES (?, ?, ?, ?)",
                      (source, key, json.dumps(payload, ensure_ascii=False), now))

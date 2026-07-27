"""真实 API 冒烟测试——手动运行，不进 unittest discover。

用途：验证各源端点与响应字段未漂移。限流友好（每源 1-2 个请求）。
运行：python3 tests/datasources/smoke_real_api.py
"""
from __future__ import annotations

import os
import pathlib
import sys
import tempfile

# 确保能 import paper_shared（复用同目录 __init__.py 的 sys.path 注入）
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "skills" / "_shared"))

from paper_shared.datasources.cache import Cache
from paper_shared.datasources.clients import CLIENT_CLASSES
from paper_shared.datasources.registry import Registry
from paper_shared.datasources.transport import Transport

KNOWN = {
    "crossref": ("lookup_doi", "10.1038/nature12373"),
    "openalex": ("lookup_doi", "10.1038/nature12373"),
    "semantic_scholar": ("lookup_doi", "10.1038/nature12373"),
    "arxiv": ("lookup_arxiv_id", "1706.03762"),
    "pubmed": ("lookup_doi", "10.1038/nature12373"),
    "eric": ("search", "education technology"),
}

OK = "\033[32m✓\033[0m"
FAIL = "\033[31m✗\033[0m"


def main() -> int:
    registry = Registry.load()
    transport = Transport(user_agent="Paper-smoke/0", mailto=os.environ.get("PAPER_MAILTO"))
    tmp = tempfile.mkdtemp()
    cache = Cache(pathlib.Path(tmp) / "smoke.db")
    exit_code = 0

    for src_id, (method, arg) in KNOWN.items():
        cls = CLIENT_CLASSES.get(src_id)
        if not cls:
            continue
        cfg = registry.get(src_id)
        from paper_shared.datasources.transport import Throttle
        interval = ((cfg.rate_limit or {}).get("anonymous") or {}).get("min_interval_s", 1.0)
        client = cls(cfg, transport, cache, Throttle(interval), fresh=True)
        api_key_env = (cfg.auth or {}).get("key_env")
        if api_key_env:
            client.api_key = os.environ.get(api_key_env)
        try:
            fn = getattr(client, method)
            result = fn(arg)
            status = OK if result else f"{FAIL} (无命中)"
            title = ""
            if hasattr(result, "metadata"):
                title = result.metadata.get("title") or ""
            elif result:
                title = str(result[0].metadata.get("title", "")) if result else ""
            print(f"  {OK} {src_id:20s} {method}({arg}) → {status} {title[:50]}")
        except Exception as e:
            print(f"  {FAIL} {src_id:20s} {method}({arg}) → {type(e).__name__}: {e}")
            exit_code = 1
    return exit_code


if __name__ == "__main__":
    print("真实 API 冒烟测试（每源 1-2 请求）...")
    sys.exit(main())

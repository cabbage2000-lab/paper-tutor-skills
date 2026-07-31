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

    # 作者端点单独走一趟：它有两个响应结构（作者实体 / 按作者过滤 works），
    # 且承载着「ORCID 能穿透源的实体拆分」这个不变量——那是 --author-works 的立身之本，
    # 一旦 OpenAlex 改了 author.orcid 过滤语义，两步作者检索会静默返回不完整的论文列表。
    from paper_shared.datasources.transport import Throttle
    cfg = registry.get("openalex")
    interval = ((cfg.rate_limit or {}).get("anonymous") or {}).get("min_interval_s", 1.0)
    client = CLIENT_CLASSES["openalex"](cfg, transport, cache, Throttle(interval), fresh=True)
    try:
        cands, total = client.find_authors("Shenghua Zhou", limit=5)
        print(f"  {OK if cands else FAIL} {'openalex':20s} find_authors → "
              f"{len(cands)}/{total} 候选，带 ORCID {sum(1 for c in cands if c.orcid)}")
        if not cands:
            exit_code = 1
        # 已知被拆成两个实体（99 + 6）的 ORCID：按 ORCID 查应显著多于按单实体查
        by_orcid = len(client.works_by_author(orcid="0000-0003-3871-9099", limit=200))
        by_entity = len(client.works_by_author(entity_id="A5041699772", limit=200))
        ok = by_orcid > by_entity
        print(f"  {OK if ok else FAIL} {'openalex':20s} works_by_author → "
              f"ORCID {by_orcid} 篇 vs 单实体 {by_entity} 篇"
              f"{'' if ok else '  ← ORCID 未能穿透实体拆分，两步作者检索会漏召回'}")
        if not ok:
            exit_code = 1
    except Exception as e:
        print(f"  {FAIL} {'openalex':20s} author endpoints → {type(e).__name__}: {e}")
        exit_code = 1
    return exit_code


if __name__ == "__main__":
    print("真实 API 冒烟测试（每源 1-2 请求）...")
    sys.exit(main())

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
    # 中文 DOI 题录通路。样本是《地理学报》2020(1) 宋长青（ISTIC 注册）——中文轨唯一的
    # 自动题录来源，且实测经 doi.org 代理到 ISTIC 自建服务（`122.115.55.36:8000`），
    # 稳定性弱于 Crossref，正是最值得定期冒烟的一条。
    "doi_meta": ("lookup_doi", "10.11821/dlxb202001001"),
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

    # 开放获取（OA）与撤稿信号单独走一趟：两者都从「已经拿回来、但曾被丢弃的字段」里提取
    # （OpenAlex 的 open_access / best_oa_location，PubMed 的 pubtype / CommentsCorrections），
    # 所以源一改字段路径就会**静默变空**——单元测试跑的是 fixture，抓不到这种漂移。
    #
    # 本机注意：eutils 经本机代理（127.0.0.1:7897）不通（curl exit 35 / SSL handshake 失败），
    # 跑这一段须直连：`no_proxy='*' python3 tests/datasources/smoke_real_api.py`。
    def _oa_probe(src_id, label, fn, expect):
        nonlocal exit_code
        try:
            oa = fn()
            missing = [k for k in expect if not (oa or {}).get(k)]
            note = "" if not missing else f"  ← 缺 {missing}，字段路径可能已漂移"
            print(f"  {OK if not missing else FAIL} {src_id:20s} {label} → {oa}{note}")
            if missing:
                exit_code = 1
        except Exception as e:
            print(f"  {FAIL} {src_id:20s} {label} → {type(e).__name__}: {e}")
            exit_code = 1

    def _client(src_id):
        cfg = registry.get(src_id)
        iv = ((cfg.rate_limit or {}).get("anonymous") or {}).get("min_interval_s", 1.0)
        c = CLIENT_CLASSES[src_id](cfg, transport, cache, Throttle(iv), fresh=True)
        env = (cfg.auth or {}).get("key_env")
        if env:
            c.api_key = os.environ.get(env)
        return c

    # 10.1056/NEJMoa2034577：实测 pdf_url 为 null、landing_page_url 有值，且开放版是
    # **投稿版**——正是「链接要两级降级」与「版本必须一起陈列」两条的来源样本。
    _oa_probe("openalex", "oa(10.1056/NEJMoa2034577)",
              lambda: _client("openalex").lookup_doi("10.1056/NEJMoa2034577").metadata["oa"],
              ("status", "url", "url_kind", "version", "host"))
    # 同一篇在 PubMed 侧有 PMC 全文（PMC7745181）→ green / pmc
    _oa_probe("pubmed", "oa(PMC 全文)",
              lambda: _client("pubmed").lookup_doi("10.1056/NEJMoa2034577").metadata["oa"],
              ("status", "url", "host"))
    _oa_probe("arxiv", "oa(1706.03762)",
              lambda: _client("arxiv").lookup_arxiv_id("1706.03762").metadata["oa"],
              ("status", "url", "url_kind", "version", "host"))

    # PMID 42371203 是一条**真撤稿**文献（2026-08-04 实测）：pubtype 含 "Retracted
    # Publication"，CommentsCorrections 的 RetractionIn 给出撤稿声明的刊期、DOI 与 PMID。
    # 撤稿声明本身（PMID 42507066）带的是 RetractionOf，绝不能被判成「已撤稿」——方向
    # 读反则撤稿态永不触发，故两条一起探。
    try:
        hits = _client("pubmed").search("42371203[uid]", limit=1)
        r = hits[0].retraction if hits else None
        ok = bool(r and r.get("doi") and r.get("notice_pmid"))
        print(f"  {OK if ok else FAIL} {'pubmed':20s} retraction(42371203) → {r}"
              f"{'' if ok else '  ← 撤稿详情未取到，CommentsCorrections 路径可能已变'}")
        if not ok:
            exit_code = 1
        notice = _client("pubmed").search("42507066[uid]", limit=1)
        clean = bool(notice) and notice[0].retraction is None
        print(f"  {OK if clean else FAIL} {'pubmed':20s} 方向陷阱(42507066 是撤稿声明本身) → "
              f"{'未被误判为已撤稿' if clean else '被误判成已撤稿——RefType 方向读反了'}")
        if not clean:
            exit_code = 1
    except Exception as e:
        print(f"  {FAIL} {'pubmed':20s} retraction → {type(e).__name__}: {e}")
        exit_code = 1
    return exit_code


if __name__ == "__main__":
    print("真实 API 冒烟测试（每源 1-2 请求）...")
    sys.exit(main())

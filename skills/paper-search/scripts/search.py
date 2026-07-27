#!/usr/bin/env python3
"""paper-search 检索 CLI。两种模式，均输出结构化 JSON 到 stdout、不写任何文件
（产物落盘由宿主按 SKILL.md 完成）：

  --query      检索模式：调门面 search() → 跨源去重 / 排序 / 分页 / 覆盖组装。
  --lookup-doi 回填模式：调门面 lookup() 查单个 DOI 元数据（中文回填补全用）；
               ISTIC 中文 DOI 无元数据时如实标"人工核对"，绝不 NOT_FOUND。

去重 / 排序是 paper-search 层的「检索策略」（数据源模块 spec §1.1 归此层）；数据源门面只
负责取证（各源各查到什么），本脚本负责规整。设计见 paper-search spec §2 / §4 / §8.6。
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys

# 标准三行引导头（同 paper-doctor/scripts/doctor.py）：parents[2] = skills/，其下 _shared/
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "_shared"))
from paper_shared.datasources import lookup as ds_lookup   # noqa: E402
from paper_shared.datasources import search as ds_search   # noqa: E402
from paper_shared.datasources.models import normalize_doi   # noqa: E402

# 跨源合并的元数据权威序（已刊元数据最权威）：crossref > openalex > s2 > arxiv > pubmed > eric
_SOURCE_RANK = {"crossref": 0, "openalex": 1, "semantic_scholar": 2,
                "arxiv": 3, "pubmed": 4, "eric": 5}


def _norm_title(title):
    """无 DOI 时的去重键：小写 + 去标点 + 折叠空白。"""
    if not title:
        return ""
    t = re.sub(r"[^\w\s]", "", str(title).lower())
    return re.sub(r"\s+", " ", t).strip()


def _dedup_key(hit):
    doi = (hit.metadata.get("doi") or "").strip().lower()
    if doi:
        return ("doi", normalize_doi(doi))
    title = _norm_title(hit.metadata.get("title"))
    if title:
        return ("title", title)
    return ("uniq", id(hit))     # 无 DOI 无标题：无法归并，各自独立


def _url(meta):
    doi = meta.get("doi")
    return f"https://doi.org/{doi}" if doi else None


def dedup_hits(items):
    """跨源去重：DOI 主键 / 无 DOI 回退规范化标题。同一文献合并成一条，sources[] 记全部命中源，
    元数据取权威序最高的源为主源（primary_source）。冲突时主源值优先，不静默丢弃其余源信息。"""
    groups = {}
    order = []
    for hit in items:
        key = _dedup_key(hit)
        if key not in groups:
            groups[key] = {"primary": hit, "sources": [hit.source]}
            order.append(key)
            continue
        g = groups[key]
        if hit.source not in g["sources"]:
            g["sources"].append(hit.source)
        if _SOURCE_RANK.get(hit.source, 99) < _SOURCE_RANK.get(g["primary"].source, 99):
            g["primary"] = hit       # 更权威源接管元数据；sources 仍累积全部
    merged = []
    for key in order:
        g = groups[key]
        h = g["primary"]
        m = h.metadata
        merged.append({
            "title": m.get("title"), "authors": m.get("authors") or [], "year": m.get("year"),
            "venue": m.get("venue"), "doi": m.get("doi"), "type": m.get("type"), "url": _url(m),
            "sources": sorted(g["sources"], key=lambda s: _SOURCE_RANK.get(s, 99)),
            "primary_source": h.source, "from_cache": h.from_cache, "retraction": h.retraction,
        })
    return merged


def rank_hits(merged, sort="year_desc"):
    """排序仅用客观、非质量键（paper-search spec 红线 1）：year_desc = 年份降序（默认，
    year 缺失排最后）；source_count = 命中源数降序。绝不用相关度 / 质量分。稳定排序可复现。"""
    if sort == "source_count":
        return sorted(merged, key=lambda m: (len(m["sources"]), m.get("year") or 0), reverse=True)
    return sorted(merged, key=lambda m: m.get("year") or 0, reverse=True)


def build_payload(query, filters, result, sort="year_desc", limit=30):
    """把门面 SearchResult 组装成脚本输出契约（paper-search spec §4.1）。"""
    merged = dedup_hits(result.items)
    ranked = rank_hits(merged, sort)
    shown = ranked[:limit]
    for i, m in enumerate(shown, 1):
        m["rank"] = i
    raw = len(result.items)
    cached = sum(1 for it in result.items if getattr(it, "from_cache", False))
    return {
        "query": query,
        "filters": filters or {},
        "network_status": result.network_status,
        "coverage": result.coverage,
        "results": shown,
        "stats": {"raw_hits": raw, "after_dedup": len(ranked), "shown": len(shown),
                  "cache_hit_rate": round(cached / raw, 3) if raw else 0.0, "sort": sort},
    }


def build_lookup_payload(doi, evidence):
    """回填补全输出：查到则给元数据；ISTIC 中文 DOI（合法但元数据 API 不可达）标人工核对，
    绝不 NOT_FOUND（paper-search spec 红线 3 / §8.4）。"""
    hit = evidence.hits[0] if evidence.hits else None
    note = None
    if evidence.doi_ra == "ISTIC":
        note = "ISTIC 注册：DOI 合法、元数据 API 不可达，请人工核对题录（不是编造嫌疑）"
    elif hit is None:
        note = "各开放源未命中：可能是中文库文献或元数据未收录，请人工核对，勿据此判定编造"
    return {"doi": doi, "doi_ra": evidence.doi_ra, "route_note": evidence.route_note,
            "found": hit is not None, "metadata": hit.metadata if hit else None, "note": note}


def _parse_args(argv):
    p = argparse.ArgumentParser(
        description="paper-search 检索 / 回填补全脚本：调开放 API 门面，输出结构化 JSON。")
    p.add_argument("--query", help="检索模式必填：已与用户共建、确认过的 API 查询串")
    p.add_argument("--lookup-doi", help="回填模式：查单个 DOI 的元数据补全（与 --query 二选一）")
    p.add_argument("--year-from", type=int, help="起始年份（含）")
    p.add_argument("--year-to", type=int, help="截止年份（含）")
    p.add_argument("--type", help="文献类型（canonical：journal-article / conference-paper / ...）")
    p.add_argument("--sources", help="逗号分隔的源 id；缺省用核心源")
    p.add_argument("--per-source", type=int, default=20, help="每源取回上限（门面 limit）")
    p.add_argument("--limit", type=int, default=30, help="去重排序后最终展示条数")
    p.add_argument("--sort", default="year_desc", choices=["year_desc", "source_count"])
    p.add_argument("--no-cache", action="store_true", help="强制刷新（投稿前终检 / 更新版图）")
    return p.parse_args(argv)


def _dump(payload):
    json.dump(payload, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")


def main(argv=None):
    args = _parse_args(argv)
    if args.lookup_doi:
        ev = ds_lookup(doi=args.lookup_doi)
        _dump(build_lookup_payload(args.lookup_doi, ev))
        return 0
    if not args.query:
        sys.stderr.write("需要 --query（检索）或 --lookup-doi（回填补全）之一\n")
        return 2
    filters = {}
    if args.year_from is not None:
        filters["year_from"] = args.year_from
    if args.year_to is not None:
        filters["year_to"] = args.year_to
    if args.type:
        filters["type"] = args.type
    sources = [s.strip() for s in args.sources.split(",")] if args.sources else None
    result = ds_search(args.query, filters=filters or None, sources=sources,
                       limit=args.per_source, fresh=args.no_cache)
    _dump(build_payload(args.query, filters or None, result, sort=args.sort, limit=args.limit))
    return 0


if __name__ == "__main__":
    sys.exit(main())

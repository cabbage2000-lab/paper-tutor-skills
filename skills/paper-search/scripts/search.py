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
import datetime
import json
import pathlib
import re
import sys

# 标准三行引导头（同 paper-doctor/scripts/doctor.py）：parents[2] = skills/，其下 _shared/
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "_shared"))
from paper_shared.datasources import lookup as ds_lookup   # noqa: E402
from paper_shared.datasources import search as ds_search   # noqa: E402
from paper_shared.datasources.clients.arxiv import usable_terms as arxiv_usable_terms  # noqa: E402
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
            # date = 日级日期（YYYY-MM-DD），供 paper-daily 判「今日 / 最近 N 天」时间窗。
            # 目前只有 arXiv 提供，其余源为 null——给不出就是 null，不猜、不用 year 凑。
            "date": m.get("date"),
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


def truncation_warning(after_dedup, shown, sort):
    """`--limit` 截掉了结果时的如实声明。判据一直在 stats 里（after_dedup 对 shown），但
    宿主不会主动去比这两个数——实况：SKILL.md 的示例参数 `--limit 30` 被照抄，74 条去重
    结果只呈现 30 条，2024 与 2023 两整年一条未进，无人察觉。`--limit` 是截断不是分页，
    默认排序又是 year_desc，所以漏的总是更早的年份、且整年成片消失。"""
    return (f"去重后 {after_dedup} 条、本次只展示 {shown} 条：--limit 是截断不是分页，"
            f"被截掉的 {after_dedup - shown} 条按当前排序（{sort}）排在后面"
            f"（year_desc 下即更早的年份，可能整年消失）；综述检索请用 "
            f"--limit {after_dedup} 或 --limit 0（不截断）重跑，不要据此判断研究空白")


def build_payload(query, filters, result, sort="year_desc", limit=30, warnings=None):
    """把门面 SearchResult 组装成脚本输出契约（paper-search spec §4.1）。"""
    merged = dedup_hits(result.items)
    ranked = rank_hits(merged, sort)
    # limit <= 0 = 不截断（综述检索要能装下全部去重结果）。CLI 只放行 0，负数在入参层挡掉。
    shown = ranked if limit is None or limit <= 0 else ranked[:limit]
    for i, m in enumerate(shown, 1):
        m["rank"] = i
    raw = len(result.items)
    cached = sum(1 for it in result.items if getattr(it, "from_cache", False))
    warns = list(warnings or [])
    if len(shown) < len(ranked):
        warns.append(truncation_warning(len(ranked), len(shown), sort))
    return {
        "query": query,
        "filters": filters or {},
        "network_status": result.network_status,
        "coverage": result.coverage,
        "results": shown,
        "warnings": warns,
        "stats": {"raw_hits": raw, "after_dedup": len(ranked), "shown": len(shown),
                  "cache_hit_rate": round(cached / raw, 3) if raw else 0.0, "sort": sort},
    }


def window_from_days(days, today=None):
    """把「最近 N 天」换成闭区间 (date_from, date_to)，含今天：days=1 就是今天当天。

    宿主 agent 自己算日期极易算错（尤其跨月），所以把这一步收进脚本。today 可注入，
    便于测试；生产调用不传，取本机当天。"""
    if days < 1:
        raise ValueError("--days 至少为 1")
    end = today or datetime.date.today()
    start = end - datetime.timedelta(days=days - 1)
    return start.isoformat(), end.isoformat()


def _valid_iso_date(s):
    """只认带横线的 `YYYY-MM-DD`。不能直接用 `date.fromisoformat` 兜底：Python 3.11 起它
    还接受无横线的 `20260729`，3.9 不接受——同一份入参在两个版本行为不同（硬规则 7 要求 3.9+）。
    更要紧的是无横线形式会流进 `_postfilter` 做字典序比较（`2026-07-29` vs `20260729`），
    比出来的结果是错的。"""
    if not isinstance(s, str) or len(s) != 10 or s[4] != "-" or s[7] != "-":
        return False
    try:
        datetime.date.fromisoformat(s)
        return True
    except ValueError:
        return False


# 日期窗口下 arXiv 走逐词 AND 布尔式，词越多越严。实测（2026-07-29，10 天窗口）：
# 3 词命中 12、5 词命中 10、7 词命中 0。超过这个数就提醒，免得把「词太多」读成「当期无新发」。
_WINDOW_TERM_WARN_AT = 5


def date_window_warnings(sources, date_from, date_to, query=None):
    """日期窗口的两处如实声明——都是为了不让 0 命中被误读：

    ① 只有 arXiv 提供日级日期，给别的源加窗口会 0 命中（源不给日期 ≠ 该源当期无新发）；
    ② 窗口下走逐词 AND，词太多会 0 命中（查询太严 ≠ 当期无新发）。
    """
    if not date_from and not date_to:
        return []
    out = []
    if sources is None:
        others_desc = "默认核心源中除 arXiv 外的源"
    else:
        others = [s for s in sources if s != "arxiv"]
        others_desc = "/".join(others) if others else None
    if others_desc:
        out.append(f"日级时间窗当前仅 arXiv 提供日期（date 字段）；{others_desc} "
                   f"在本次窗口下将 0 命中，这是源不给日期、不是该源当期无新发")
    terms = len((query or "").split())
    if terms > _WINDOW_TERM_WARN_AT:
        out.append(f"日级时间窗下 arXiv 走逐词 AND 布尔式，本次 {terms} 个词需全部出现；"
                   f"若 0 命中请先换 2-5 个核心概念词重试，不要据此判定当期无新发")
    return out


def build_lookup_payload(doi, evidence):
    """回填补全输出：查到则给元数据；查不到分三档如实说清证据强度——ISTIC 中文 DOI（合法但
    元数据 API 不可达）、前缀未注册（不存在的强信号）、各源未命中（可能只是未收录）。三档
    一律交人工核对、绝不 NOT_FOUND（paper-search spec 红线 3 / §8.4）。"""
    hit = evidence.hits[0] if evidence.hits else None
    note = None
    if evidence.doi_ra == "ISTIC":
        note = "ISTIC 注册：DOI 合法、元数据 API 不可达，请人工核对题录（不是编造嫌疑）"
    elif evidence.doi_ra == "not_registered":
        # 与下一档的区别：前缀未注册是「不存在」的强信号（路由压根不查任何源，见 routing.route），
        # 各源未命中很可能只是中文库未收录。两者都交人工核对（存在性判定归 paper-verify），
        # 但证据强度必须如实分开——共用同一句会把编造 DOI 与真实中文文献抹平。
        note = ("DOI 前缀未在任一注册机构注册（因此未查任何元数据源）：这是 DOI 不存在的强信号，"
                "请人工核对来源；存在性判定请走 /paper-verify")
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
    p.add_argument("--date-from", help="起始日期（含），ISO YYYY-MM-DD；日级时间窗仅 arXiv 支持")
    p.add_argument("--date-to", help="截止日期（含），ISO YYYY-MM-DD")
    p.add_argument("--days", type=int,
                   help="最近 N 天（含今天）：--days 1 = 今日。与 --date-from/--date-to 互斥")
    p.add_argument("--type", help="文献类型（canonical：journal-article / conference-paper / ...）")
    p.add_argument("--sources", help="逗号分隔的源 id；缺省用核心源")
    p.add_argument("--per-source", type=int, default=20, help="每源取回上限（门面 limit）")
    p.add_argument("--limit", type=int, default=30,
                   help="去重排序后最终展示条数；0 = 不截断（综述检索用，全量呈现去重结果）")
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
    if args.limit < 0:
        # 0 有明确语义（不截断），负数只可能是手滑。同 --days，宁可报错也不静默做怪事。
        sys.stderr.write(f"--limit 不能为负（0 = 不截断），收到：{args.limit}\n")
        return 2
    filters = {}
    if args.year_from is not None:
        filters["year_from"] = args.year_from
    if args.year_to is not None:
        filters["year_to"] = args.year_to
    if args.type:
        filters["type"] = args.type
    date_from, date_to = args.date_from, args.date_to
    if args.days is not None:
        if date_from or date_to:
            sys.stderr.write("--days 与 --date-from/--date-to 互斥，二选一\n")
            return 2
        if args.days < 1:
            sys.stderr.write("--days 至少为 1（--days 1 = 今日）\n")
            return 2
        date_from, date_to = window_from_days(args.days)
    for label, value in (("--date-from", date_from), ("--date-to", date_to)):
        if value and not _valid_iso_date(value):
            sys.stderr.write(f"{label} 需为 ISO 日期 YYYY-MM-DD，收到：{value}\n")
            return 2
    if date_from and date_to and date_from > date_to:
        sys.stderr.write(f"日期窗口起点晚于终点：{date_from} > {date_to}\n")
        return 2
    if (date_from or date_to) and arxiv_usable_terms(args.query) < 1:
        # 带窗口时查询要组成逐词布尔式，一个可用词都切不出来就没法查。宁可报错，
        # 也不能只留日期条件去查——那会把窗口内的全站新发当成用户主题的新发。
        sys.stderr.write(f"带日期窗口时 --query 至少要有一个可用检索词，收到：{args.query}\n")
        return 2
    if date_from:
        filters["date_from"] = date_from
    if date_to:
        filters["date_to"] = date_to
    sources = [s.strip() for s in args.sources.split(",")] if args.sources else None
    result = ds_search(args.query, filters=filters or None, sources=sources,
                       limit=args.per_source, fresh=args.no_cache)
    _dump(build_payload(args.query, filters or None, result, sort=args.sort, limit=args.limit,
                        warnings=date_window_warnings(sources, date_from, date_to, args.query)))
    return 0


if __name__ == "__main__":
    sys.exit(main())

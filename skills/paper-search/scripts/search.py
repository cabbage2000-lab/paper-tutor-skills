#!/usr/bin/env python3
"""paper-search 检索 CLI。三种模式，均输出结构化 JSON 到 stdout、不写任何文件
（产物落盘由宿主按 SKILL.md 完成）：

  --query      检索模式：调门面 search() → 跨源去重 / 排序 / 分页 / 覆盖组装。
  --snowball   滚雪球模式：调门面 related() 由一篇已知文献取参考文献（后向）与被引
               文献（前向）。输出与 --query 同形，可并进同一张笔记表。
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
from paper_shared.datasources import lookup as ds_lookup     # noqa: E402
from paper_shared.datasources import related as ds_related   # noqa: E402
from paper_shared.datasources import search as ds_search     # noqa: E402
from paper_shared.datasources.clients.arxiv import usable_terms as arxiv_usable_terms  # noqa: E402
from paper_shared.datasources.clients.base import canonical_type  # noqa: E402
from paper_shared.datasources.models import Ref, normalize_doi   # noqa: E402
from paper_shared.matching import compare_fields, pick_best_hit  # noqa: E402

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


def _merge_cited_by(hits):
    """被引数跨源取**最大值**并记下来源源名。

    各库口径本就不同（Crossref 只数注册了 DOI 的引用、OpenAlex 含预印本、S2 收更多灰色
    文献），没有哪个是"正确"的。取最大是「至少有这么多」的下界陈述，配上来源标注，用户
    自己能判断口径；静默取主源值则会让同一篇在换个主源后数字突变、且看不出为什么。

    只有 int 参与比较：源不给这个字段是 None，与真实的 0（确实零被引）严格区分——
    bool 是 int 的子类，显式排掉，免得 True 被当成 1。
    """
    best, src = None, None
    for h in hits:
        v = h.metadata.get("cited_by_count")
        if isinstance(v, int) and not isinstance(v, bool) and (best is None or v > best):
            best, src = v, h.source
    return best, src


def _merge_abstract(hits):
    """摘要按权威序取第一个非空值。

    与题录字段不同：题录取权威序是因为已刊元数据最准，而摘要不存在"谁的更权威"——
    它要么有要么没有。Crossref 为主源的条目常常没摘要（本项目不解析它的 JATS 片段），
    此时从 OpenAlex / S2 补是净收益，不补则起草档直接少一批条目。
    """
    for h in sorted(hits, key=lambda x: _SOURCE_RANK.get(x.source, 99)):
        a = h.metadata.get("abstract")
        if a and str(a).strip():
            return str(a).strip(), h.source
    return None, None


def _merge_author_details(hits):
    """作者标识取「认得出的人最多」的那个源，不按权威序取第一个非空。

    与摘要那条不同：摘要是有无问题，作者标识是**覆盖度**问题。实测同一批结果里 Crossref
    的 ORCID 覆盖 4%、OpenAlex 78%，而 Crossref 恰恰是权威序最高的主源——按权威序取，
    绝大多数条目的 ORCID 会凭空消失。

    **整份取、绝不跨源拼**：各源的作者列表长度与顺序都可能不同，按名字把两个源的标识
    拼起来，就是在判定「这两条说的是不是同一个人」——那正是本层不做的事。带 ORCID 数
    相同时权威序在前的胜出（sorted 保证），结果可复现。
    """
    best, src, score = None, None, -1
    for h in sorted(hits, key=lambda x: _SOURCE_RANK.get(x.source, 99)):
        details = h.metadata.get("author_details") or []
        if not details:
            continue            # 空的不参与竞争，否则会盖掉后面真有内容的源
        n = sum(1 for d in details if d.get("orcid"))
        if n > score:
            best, src, score = details, h.source, n
    return best, src


def dedup_hits(items):
    """跨源去重：DOI 主键 / 无 DOI 回退规范化标题。同一文献合并成一条，sources[] 记全部命中源，
    元数据取权威序最高的源为主源（primary_source）。冲突时主源值优先，不静默丢弃其余源信息。

    被引数与摘要是两个例外，不走「主源优先」（各自理由见 _merge_cited_by / _merge_abstract）。"""
    groups = {}
    order = []
    for hit in items:
        key = _dedup_key(hit)
        if key not in groups:
            groups[key] = {"primary": hit, "sources": [hit.source], "hits": [hit]}
            order.append(key)
            continue
        g = groups[key]
        g["hits"].append(hit)
        if hit.source not in g["sources"]:
            g["sources"].append(hit.source)
        if _SOURCE_RANK.get(hit.source, 99) < _SOURCE_RANK.get(g["primary"].source, 99):
            g["primary"] = hit       # 更权威源接管元数据；sources 仍累积全部
    merged = []
    for key in order:
        g = groups[key]
        h = g["primary"]
        m = h.metadata
        cited, cited_src = _merge_cited_by(g["hits"])
        abstract, abstract_src = _merge_abstract(g["hits"])
        author_details, author_details_src = _merge_author_details(g["hits"])
        # 滚雪球方向：同一篇可能既在后向又在前向出现（互引），两向都要留，不二选一
        directions = []
        for x in g["hits"]:
            d = x.metadata.get("snowball_direction")
            if d and d not in directions:
                directions.append(d)
        merged.append({
            "title": m.get("title"), "authors": m.get("authors") or [], "year": m.get("year"),
            # 作者的客观标识（ORCID / 机构）与它的来源库。**可能与 authors 不是同一个源**
            # （authors 跟主源，标识跟覆盖最好的源），所以每条自带 name、不靠下标对应，
            # 且必须连 author_details_source 一起呈现。null = 各源都没给标识。
            "author_details": author_details, "author_details_source": author_details_src,
            # date = 日级日期（YYYY-MM-DD），供 paper-daily 判「今日 / 最近 N 天」时间窗。
            # 目前只有 arXiv 提供，其余源为 null——给不出就是 null，不猜、不用 year 凑。
            "date": m.get("date"),
            "venue": m.get("venue"), "doi": m.get("doi"), "type": m.get("type"), "url": _url(m),
            # 被引数与它的来源库：null = 各源都没给这个数（不是零被引）
            "cited_by_count": cited, "cited_by_source": cited_src,
            "abstract": abstract, "abstract_source": abstract_src,
            "sources": sorted(g["sources"], key=lambda s: _SOURCE_RANK.get(s, 99)),
            "primary_source": h.source, "from_cache": h.from_cache, "retraction": h.retraction,
        })
        if directions:
            merged[-1]["snowball_directions"] = directions
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
    默认排序又是 year_desc，所以漏的总是更早的年份、且整年成片消失。

    `--limit` 的默认值此后改为 0（不截断），所以本告警只在**调用方显式传了正数**时触发。
    默认值改了，告警仍要留着：显式截断同样会让整年消失，只是这次是调用方自找的。"""
    return (f"去重后 {after_dedup} 条、本次只展示 {shown} 条：--limit 是截断不是分页，"
            f"被截掉的 {after_dedup - shown} 条按当前排序（{sort}）排在后面"
            f"（year_desc 下即更早的年份，可能整年消失）；要全量请去掉 --limit "
            f"（默认即不截断）或显式传 --limit 0，不要据此判断研究空白")


# ---- 分布 advisory（红线 1 的量化形态：给证据与比例，不给结论）----

_ADVISORY_MIN_KNOWN = 5      # 该维度有值的条目少于这个数就不发：比例失去意义，只剩噪声
_ADVISORY_THRESHOLD = 0.70   # 单一取值占比达到即提示


def _year_bucket(year):
    """年份按 5 年一档聚。用档而不是具体年份：单一年份占到七成几乎只在结果极少时发生，
    而「七成结果挤在最近 5 年」才对得上 Research Gap 五类里的「时间缺失」——它同时正是
    滚雪球后向（补经典文献）的触发条件。"""
    if not isinstance(year, int) or isinstance(year, bool):
        return None
    b = (year // 5) * 5
    return f"{b}–{b + 4}"


# 只用题录元数据算得出的四个维度。方法 / 研究场景**有意不算**：元数据里推不出来，
# 硬给百分比等于编。那两项由宿主按真实摘要定性描述（见 SKILL.md），不带比例。
_ADVISORY_DIMS = (
    ("发表年份（5 年一档）", lambda m: _year_bucket(m.get("year"))),
    ("发表期刊 / 来源", lambda m: (m.get("venue") or "").strip() or None),
    # 类型必须先归一到 canonical 再统计：Crossref 说 journal-article、OpenAlex 说 article，
    # 同一类型的两种源方言。不归一就会把真实的集中劈成两半——实测 20 条结果里 10+9 条其实
    # 全是期刊论文（95%），分方言统计后最高只有 50%，advisory 直接漏报。
    # 归一不了的保留原值（不是丢掉）：丢掉会缩小分母，又是一次稀释。
    ("文献类型", lambda m: canonical_type(m.get("type")) or m.get("type") or None),
    ("主命中源", lambda m: m.get("primary_source") or None),
)


def distribution_advisories(shown):
    """各维度的单值集中度达阈值就出一条。

    **与 warnings 分开放**（build_payload 里是两个字段）：warnings 说「这次检索有问题」
    （被截断了 / 时间窗对该源不适用），advisories 说「这批结果长这样」。后者不是故障，
    混进同一个列表会让宿主把分布特征当异常念给用户听。

    分母用该维度**有值的条目数** known，不是总条数：venue 缺一半时拿总数当分母，真实的
    集中会被稀释到阈值以下，信号就消失了。
    """
    out = []
    for label, get in _ADVISORY_DIMS:
        values = [v for v in (get(m) for m in shown) if v is not None and v != ""]
        known = len(values)
        if known < _ADVISORY_MIN_KNOWN:
            continue
        counts = {}
        for v in values:
            counts[v] = counts.get(v, 0) + 1
        # 平局时按取值字符串取大者，保证同一批结果每次跑出同一条 advisory（可复现）
        top, n = max(counts.items(), key=lambda kv: (kv[1], str(kv[0])))
        if n / known < _ADVISORY_THRESHOLD:
            continue
        pct = round(n * 100 / known)
        out.append({
            "dimension": label, "value": str(top), "count": n, "known": known, "pct": pct,
            "text": (f"{label}：{top} = {n}/{known}（{pct}%）。"
                     f"这是分布信号，不是缺陷；是否需要拓宽检索范围由你判断。"),
        })
    return out


def build_payload(query, filters, result, sort="year_desc", limit=0, warnings=None,
                  mode="search"):
    """把门面 SearchResult 组装成脚本输出契约（paper-search spec §4.1）。

    检索与滚雪球共用本函数（mode 只进输出、不改逻辑）：两者的结果要能并进同一张笔记表，
    输出同形是前提。"""
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
        "mode": mode,
        "query": query,
        "filters": filters or {},
        "network_status": result.network_status,
        "coverage": result.coverage,
        "results": shown,
        "warnings": warns,
        # 分布算在 **ranked（截断前）** 上，不是 shown：截断是呈现层的事，分布是检索层的
        # 事实。算在 shown 上会让 `--limit 10` 配 year_desc 必然报出「年份高度集中」——
        # 那个集中是 limit 造出来的假信号。分母对不上 results 行数时看 stats.after_dedup。
        "advisories": distribution_advisories(ranked),
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


def build_lookup_payload(doi, evidence, ref=None):
    """回填补全输出：查到则给元数据；查不到分三档如实说清证据强度——ISTIC 中文 DOI（合法但
    元数据 API 不可达）、前缀未注册（不存在的强信号）、各源未命中（可能只是未收录）。三档
    一律交人工核对、绝不 NOT_FOUND（paper-search spec 红线 3 / §8.4）。

    `ref` 非空且带标题时，额外把手里的题录与命中元数据做一次交叉核验（共享内核
    `paper_shared.matching`，与 paper-verify 同一套阈值），堵的是「DOI 解析得开、指向的
    却是另一篇」——DOI 抄错一位、或题录张冠李戴时都会这样，光看 `found=true` 发现不了。

    **这里只陈列比对结果，不判态**：`field_notes` 原样给宿主转述，出口指引仍是
    `/paper-verify`。存在性判定不归本命令（红线 3），加了比对也不归。
    """
    hits = evidence.hits
    # 多源命中时按题录选最匹配的那条，而不是取 hits[0]（各源题录可能差异很大）；
    # 没给 ref 就维持原行为。
    hit = (pick_best_hit(ref, hits) if (ref is not None and hits) else
           (hits[0] if hits else None))
    field_notes = None
    metadata_consistent = None
    # 只在「调用方给了标题」时比对。没给就是 None（未比对），绝不拿源自己的标题自比出一个
    # 假的 True——那会把「没核对过」说成「核对一致」。
    if hit is not None and ref is not None and ref.title:
        notes = compare_fields(ref, hit)
        field_notes = [n.to_dict() for n in notes]
        metadata_consistent = not any(n.severity == "mismatch" for n in notes)
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
    elif metadata_consistent is False:
        note = ("DOI 查得到，但你给的题录与源元数据对不上（见 field_notes）：常见成因是 DOI "
                "抄错一位、或题录与 DOI 张冠李戴。请核对这条 DOI 的来源后再决定是否入表；"
                "存在性判定请走 /paper-verify")
    return {"doi": doi, "doi_ra": evidence.doi_ra, "route_note": evidence.route_note,
            "found": hit is not None, "metadata": hit.metadata if hit else None,
            # null = 未比对（没给 --title 或没查到），与 false（比对了且不一致）严格区分
            "metadata_consistent": metadata_consistent, "field_notes": field_notes,
            "note": note}


def _parse_args(argv):
    p = argparse.ArgumentParser(
        description="paper-search 检索 / 回填补全脚本：调开放 API 门面，输出结构化 JSON。")
    p.add_argument("--query", help="检索模式必填：已与用户共建、确认过的 API 查询串")
    p.add_argument("--snowball", metavar="DOI",
                   help="滚雪球模式：由这篇文献取参考文献 / 被引文献（与 --query 互斥）")
    p.add_argument("--direction", default="both",
                   choices=["backward", "forward", "both"],
                   help="滚雪球方向：backward=本文引了谁（补经典）/ forward=谁引了本文"
                        "（补跟进）/ both（默认）")
    p.add_argument("--lookup-doi", help="回填模式：查单个 DOI 的元数据补全（与 --query 二选一）")
    # 下面两个只在 --lookup-doi 模式生效：把手里的题录一并交上来做交叉核验。
    # 有意**不提供 --authors**：中文题录的作者是汉字、英文源多给拼音，姓氏候选集合必然
    # 无交集 → 系统性误报，而低误报优先（同 matching.surname_candidates 的取向）。
    # DOI + 标题 + 年份三项已足够判「是不是同一篇」。门面本身收 authors，将来要加只是加个参数。
    p.add_argument("--title", help="回填模式可选：你手里那条题录的标题，用于与源元数据交叉核验")
    p.add_argument("--ref-year", type=int,
                   help="回填模式可选：你手里那条题录的年份（与 --year-from/--year-to 无关，"
                        "那两个是检索筛选）")
    p.add_argument("--year-from", type=int, help="起始年份（含）")
    p.add_argument("--year-to", type=int, help="截止年份（含）")
    p.add_argument("--date-from", help="起始日期（含），ISO YYYY-MM-DD；日级时间窗仅 arXiv 支持")
    p.add_argument("--date-to", help="截止日期（含），ISO YYYY-MM-DD")
    p.add_argument("--days", type=int,
                   help="最近 N 天（含今天）：--days 1 = 今日。与 --date-from/--date-to 互斥")
    p.add_argument("--type", help="文献类型（canonical：journal-article / conference-paper / ...）")
    p.add_argument("--sources", help="逗号分隔的源 id；缺省用核心源")
    p.add_argument("--per-source", type=int, default=20, help="每源取回上限（门面 limit）")
    p.add_argument("--limit", type=int, default=0,
                   help="去重排序后最终展示条数；**默认 0 = 不截断**（综述检索要全量）。"
                        "传了正数就是截断，被截掉的部分会在 warnings 里如实声明")
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
        # 查询照旧只按 DOI 走（title 传进门面会改变查询行为）；题录只用于查回来之后的比对。
        ref = Ref(id="lookup", doi=args.lookup_doi, title=args.title, year=args.ref_year)
        _dump(build_lookup_payload(args.lookup_doi, ev, ref))
        return 0
    if args.query and args.snowball:
        sys.stderr.write("--query 与 --snowball 互斥，二选一\n")
        return 2
    if not args.query and not args.snowball:
        sys.stderr.write("需要 --query（检索）、--snowball（滚雪球）或 "
                         "--lookup-doi（回填补全）之一\n")
        return 2
    if args.limit < 0:
        # 0 有明确语义（不截断），负数只可能是手滑。同 --days，宁可报错也不静默做怪事。
        sys.stderr.write(f"--limit 不能为负（0 = 不截断），收到：{args.limit}\n")
        return 2
    if args.snowball:
        sources = [s.strip() for s in args.sources.split(",")] if args.sources else None
        result = ds_related(args.snowball, direction=args.direction, sources=sources,
                            limit=args.per_source, fresh=args.no_cache)
        _dump(build_payload(args.snowball, {"direction": args.direction}, result,
                            sort=args.sort, limit=args.limit, mode="snowball"))
        return 0
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

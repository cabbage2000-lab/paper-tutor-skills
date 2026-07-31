"""数据源模块公共门面（spec·第 6.1 节）。

四个入口：lookup（单条）、fetch_batch（批量，verify 主路径）、search（检索，
search 主路径）、probe_all（探测，paper-doctor）。内部参数 _registry / _transport /
_cache 以下划线前缀供测试注入；不传时用默认实例。
"""
from __future__ import annotations

import pathlib
from typing import Any, Callable, Dict, List, Optional

from .batch import BatchEngine
from .cache import Cache
from .clients import build_clients
from .models import (BatchResult, Evidence, Ref, SearchResult, SourceHit)
from .probe import ProbeEngine
from .registry import Registry
from .transport import Transport, TransportError

__all__ = ["lookup", "fetch_batch", "search", "related", "probe_all"]

# 滚雪球方向 → 需要的源能力。backward = 本文引了谁（补经典），forward = 谁引了本文（补跟进）。
_DIRECTION_CAPS = {"backward": ("references",),
                   "forward": ("cited_by",),
                   "both": ("references", "cited_by")}
_CAP_LABEL = {"references": "后向（本文引了谁）", "cited_by": "前向（谁引了本文）"}


def _defaults(registry, transport, cache):
    registry = registry or Registry.load()
    transport = transport or Transport(user_agent="Paper-datasources/0")
    cache = cache or Cache()
    return registry, transport, cache


# search 的 filters 由这些源原生映射为查询参数；其余源靠客户端侧 _postfilter 兜底
_NATIVE_FILTER_SOURCES = {"crossref", "openalex", "semantic_scholar"}


def _applied_filters(src_id: str, filters: Optional[Dict[str, Any]]) -> str:
    if not filters:
        return "none"
    return "native" if src_id in _NATIVE_FILTER_SOURCES else "client_side"


def lookup(doi: Optional[str] = None, title: Optional[str] = None,
           authors: Optional[List[str]] = None, year: Optional[int] = None,
           *, _registry: Optional[Registry] = None,
           _transport: Optional[Transport] = None,
           _cache: Optional[Cache] = None) -> Evidence:
    if not doi and not title:
        raise ValueError("lookup 至少需要 doi 或 title")
    ref = Ref(id="single", doi=doi, title=title, authors=list(authors or []),
              year=year)
    result = fetch_batch([ref], _registry=_registry, _transport=_transport, _cache=_cache)
    return result.evidences["single"]


def fetch_batch(refs: List[Ref], state_path: Optional[pathlib.Path] = None,
                progress: Optional[Callable[[str], None]] = None, fresh: bool = False,
                *, _registry: Optional[Registry] = None,
                _transport: Optional[Transport] = None,
                _cache: Optional[Cache] = None) -> BatchResult:
    registry, transport, cache = _defaults(_registry, _transport, _cache)
    engine = BatchEngine(registry, transport=transport, cache=cache, fresh=fresh,
                         state_path=state_path, progress=progress)
    return engine.run(refs)


def search(query: str, filters: Optional[Dict[str, Any]] = None,
           sources: Optional[List[str]] = None, limit: int = 20, fresh: bool = False,
           *, _registry: Optional[Registry] = None,
           _transport: Optional[Transport] = None,
           _cache: Optional[Cache] = None) -> SearchResult:
    registry, transport, cache = _defaults(_registry, _transport, _cache)
    if sources is None:
        sources = [s.id for s in registry.with_capability("search")
                   if s.role == "core"]
    clients = build_clients(registry, transport, cache, fresh=fresh, only=sources)
    items: List[SourceHit] = []
    coverage: List[Dict[str, Any]] = []
    core_attempted = core_failed = api_failed = 0
    has_degraded = False
    for src_id in sources:
        if src_id not in clients:
            continue
        cfg = registry.get(src_id)
        is_core = cfg.role == "core"
        if is_core:
            core_attempted += 1
        try:
            hits = clients[src_id].search(query, filters=filters, limit=limit)
        except TransportError as e:
            # 单源失败不中断整轮（对齐 fetch_batch 韧性）；如实标「未覆盖（网络故障）」
            api_failed += 1
            if is_core:
                core_failed += 1
            coverage.append({"source": src_id, "name_zh": cfg.name_zh, "coverage": "未覆盖",
                             "hit_count": 0, "outcome": "error", "error": e.code,
                             "applied_filters": _applied_filters(src_id, filters)})
            continue
        outcome = "ok" if hits else "empty"
        # Semantic Scholar 无 key 走慢速降级档（数据源 spec §5 组件 7）——有产出时标 degraded
        if (src_id == "semantic_scholar"
                and getattr(clients[src_id], "api_key", None) is None and hits):
            outcome = "degraded"
        if outcome == "degraded":
            has_degraded = True
        coverage.append({"source": src_id, "name_zh": cfg.name_zh, "coverage": "自动检索",
                         "hit_count": len(hits), "outcome": outcome, "error": None,
                         "applied_filters": _applied_filters(src_id, filters)})
        items.extend(hits)
    # guided 源出现在覆盖声明中（未自动检索，需用户回填）
    for guided in registry.guided_sources():
        coverage.append({"source": guided.id, "name_zh": guided.name_zh, "coverage": "需用户回填",
                         "hit_count": 0, "outcome": "n/a", "error": None, "applied_filters": "n/a"})
    if core_attempted > 0 and core_failed == core_attempted:
        network_status = "offline"           # 被检索的核心源全部失败
    elif core_failed or api_failed or has_degraded:
        network_status = "degraded"          # 部分源失败或有降级源
    else:
        network_status = "ok"
    return SearchResult(items=items, coverage=coverage, network_status=network_status)


def related(doi: str, direction: str = "both", sources: Optional[List[str]] = None,
            limit: int = 50, fresh: bool = False,
            *, _registry: Optional[Registry] = None,
            _transport: Optional[Transport] = None,
            _cache: Optional[Cache] = None) -> SearchResult:
    """滚雪球：由一篇已知文献取它的参考文献（后向）与被引文献（前向）。

    返回 SearchResult，与 search() 同形——调用方（paper-search 的 --snowball）因此能
    直接复用同一套去重 / 排序 / 输出契约，滚雪球结果与检索结果并进同一张笔记表。

    逐源逐向容错：openalex 的后向挂了不影响它的前向，更不影响 s2 两向（对齐 search()
    的韧性）。每个「源 × 方向」在 coverage 里各占一行，不合并——合并会让「前向查到了、
    后向没查到」看起来像整源失败。
    """
    if direction not in _DIRECTION_CAPS:
        raise ValueError(f"direction 需为 backward / forward / both，收到：{direction}")
    registry, transport, cache = _defaults(_registry, _transport, _cache)
    caps = _DIRECTION_CAPS[direction]
    if sources is None:
        sources = [s.id for s in registry.all()
                   if s.role == "core" and any(c in s.capabilities for c in caps)]
    clients = build_clients(registry, transport, cache, fresh=fresh, only=sources)
    items: List[SourceHit] = []
    coverage: List[Dict[str, Any]] = []
    attempted = failed = 0
    for src_id in sources:
        if src_id not in clients:
            continue
        cfg = registry.get(src_id)
        for cap in caps:
            if cap not in cfg.capabilities:
                continue                      # 该源不做这一向，不记行（它没被要求做）
            attempted += 1
            try:
                hits = getattr(clients[src_id], cap)(doi, limit=limit)
            except TransportError as e:
                failed += 1
                coverage.append({"source": src_id, "name_zh": cfg.name_zh,
                                 "coverage": "未覆盖", "hit_count": 0, "outcome": "error",
                                 "error": e.code, "direction": _CAP_LABEL[cap]})
                continue
            for h in hits:
                # 方向进 metadata：「这是它引的」与「这是引它的」对用户是两件事，
                # 去重合并后仍要能分辨（见 search.py 的 dedup_hits）。
                h.metadata["snowball_direction"] = cap
            coverage.append({"source": src_id, "name_zh": cfg.name_zh,
                             "coverage": "自动检索（滚雪球）", "hit_count": len(hits),
                             "outcome": "ok" if hits else "empty", "error": None,
                             "direction": _CAP_LABEL[cap]})
            items.extend(hits)
    # 中文库不支持滚雪球（无 API），如实占位——覆盖声明不能因为换了模式就少一块
    for guided in registry.guided_sources():
        coverage.append({"source": guided.id, "name_zh": guided.name_zh,
                         "coverage": "未覆盖（无 API，滚雪球不适用）", "hit_count": 0,
                         "outcome": "n/a", "error": None, "direction": "—"})
    if attempted > 0 and failed == attempted:
        network_status = "offline"
    elif failed:
        network_status = "degraded"
    else:
        network_status = "ok"
    return SearchResult(items=items, coverage=coverage, network_status=network_status)


def probe_all(include_supplementary: bool = True,
              *, _registry: Optional[Registry] = None,
              _transport: Optional[Transport] = None,
              _cache: Optional[Cache] = None) -> List:
    registry, transport, cache = _defaults(_registry, _transport, _cache)
    engine = ProbeEngine(registry, transport=transport, cache=cache,
                         include_supplementary=include_supplementary)
    return engine.run()

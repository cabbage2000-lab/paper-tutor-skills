"""数据契约层：本模块与 skill 之间的全部输入输出结构。

设计依据：docs/specs/2026-07-22-数据源模块设计.md·第 6 节。
文件契约与库契约同构——skill 的 CLI 对 to_dict() 结果直接 json.dump。
"""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# SourceQuery.error 的取值全集（spec·第 9 节）
ERROR_CODES = ("TIMEOUT", "CONN_FAILED", "DNS_FAIL",
               "RATE_LIMITED", "SERVER_ERROR", "PARSE_ERROR")

_DOI_URL_PREFIXES = ("https://doi.org/", "http://doi.org/", "doi.org/", "doi:")


def normalize_doi(s: str) -> str:
    """DOI 规范化：去 URL/scheme 前缀、去首尾空白、统一小写。"""
    t = s.strip()
    low = t.lower()
    for p in _DOI_URL_PREFIXES:
        if low.startswith(p):
            t = t[len(p):]
            low = t.lower()
    return t.strip().lower()


@dataclass
class Ref:
    """一条待查证的引用条目（调用方给 id，raw_text 供人工核对包引用原文）。"""
    id: str
    doi: Optional[str] = None
    title: Optional[str] = None
    authors: List[str] = field(default_factory=list)
    year: Optional[int] = None
    raw_text: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Ref":
        return cls(id=d["id"], doi=d.get("doi"), title=d.get("title"),
                   authors=list(d.get("authors") or []), year=d.get("year"),
                   raw_text=d.get("raw_text"))


@dataclass
class SourceQuery:
    """一次源查询的记录——核验报告「已查源清单与查询式样」的直接来源。"""
    source: str
    query_kind: str            # "doi" | "title_match"
    outcome: str               # "hit" | "miss" | "error"
    error: Optional[str] = None    # ∈ ERROR_CODES
    from_cache: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "SourceQuery":
        return cls(source=d["source"], query_kind=d["query_kind"],
                   outcome=d["outcome"], error=d.get("error"),
                   from_cache=bool(d.get("from_cache", False)))


@dataclass
class SourceHit:
    """一个源的命中：规范化元数据 + 裁剪后的原始响应（供 verify 逐字段比对）。"""
    source: str
    metadata: Dict[str, Any]   # title / authors[] / year / venue / doi / type
    fetched_at: str            # ISO 8601（UTC）
    retraction: Optional[Dict[str, Any]] = None   # Crossref update-to（Retraction Watch）
    raw: Dict[str, Any] = field(default_factory=dict)
    from_cache: bool = False   # 本次命中是否来自本地缓存（供 stats 缓存命中率统计）

    def to_dict(self) -> Dict[str, Any]:
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "SourceHit":
        return cls(source=d["source"], metadata=dict(d.get("metadata") or {}),
                   fetched_at=d["fetched_at"], retraction=d.get("retraction"),
                   raw=dict(d.get("raw") or {}),
                   from_cache=bool(d.get("from_cache", False)))


@dataclass
class Evidence:
    """一条引用的证据包——六态判定（paper-verify）的输入，本模块的最终产出。"""
    ref_id: str
    input: Ref
    doi_ra: Optional[str] = None   # Crossref|DataCite|ISTIC|not_registered|unknown|ra_unreachable|None(无DOI)
    route_note: Optional[str] = None
    queries: List[SourceQuery] = field(default_factory=list)
    hits: List[SourceHit] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return dataclasses.asdict(self)   # 递归展开嵌套 Ref/SourceQuery/SourceHit

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Evidence":
        return cls(ref_id=d["ref_id"], input=Ref.from_dict(d["input"]),
                   doi_ra=d.get("doi_ra"), route_note=d.get("route_note"),
                   queries=[SourceQuery.from_dict(q) for q in d.get("queries") or []],
                   hits=[SourceHit.from_dict(h) for h in d.get("hits") or []])


@dataclass
class BatchResult:
    """批任务结果：证据包集合 + 任务级统计 + 网络状态。"""
    evidences: Dict[str, Evidence]
    stats: Dict[str, Any]
    network_status: str = "ok"     # ok | degraded | offline

    def to_dict(self) -> Dict[str, Any]:
        return dataclasses.asdict(self)   # asdict 递归 Dict[str, Evidence] 的值


@dataclass
class ProbeResult:
    """健康探测结果。status 用英文态码（语言规范：态码留给日志与契约），
    paper-doctor 的用户可见报告层转中文（可用 / 不可用 / 部分可用）。"""
    source: str
    status: str                # ok | unavailable | partial
    role: str                  # core | supplementary
    reason: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return dataclasses.asdict(self)


@dataclass
class SearchResult:
    """检索结果 + 覆盖方式声明（由注册表生成，见 spec·6.2）+ 网络状态。

    network_status 与 BatchResult 同义（ok/degraded/offline）：offline = 被检索的核心源
    全部失败；degraded = 部分核心源失败，或有降级源（如 S2 无 key 慢速档）；否则 ok。
    coverage 项承载 hit_count/outcome/error/applied_filters（含非字符串值），故值类型放宽为 Any。
    """
    items: List[SourceHit]
    coverage: List[Dict[str, Any]]
    network_status: str = "ok"     # ok | degraded | offline

    def to_dict(self) -> Dict[str, Any]:
        return dataclasses.asdict(self)

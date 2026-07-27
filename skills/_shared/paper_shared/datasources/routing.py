"""DOI 注册机构（RA）判别与路由计划（spec·第 5 节组件 5）。

带 DOI 条目先分流再查证：Crossref 注册走正常核验；DataCite（含 arXiv
10.48550）经 openalex/arxiv 兜接；ISTIC（中文 DOI）不查任何源、直接携带
「DOI 合法存在、元数据 API 不可达」标记——防止 Crossref 未命中被误读成
编造嫌疑（真实中文文献误伤 = 0 的硬门槛）。前缀级缓存：同前缀只判一次。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from .cache import Cache
from .models import normalize_doi
from .transport import NotFoundError, Throttle, Transport, TransportError

RA_ENDPOINT = "https://doi.org/ra/"
RA_ROUTES = {
    "Crossref": ["crossref", "openalex"],
    "DataCite": ["openalex", "arxiv"],
    "ISTIC": [],
}
CONSERVATIVE_SOURCES = ["crossref", "openalex"]

ISTIC_NOTE = ("ISTIC（中文 DOI）注册：DOI 合法存在，注册机构未提供免费元数据 API，"
              "应走人工核对流程，绝非编造嫌疑")


@dataclass
class RoutePlan:
    doi_ra: str
    sources: List[str] = field(default_factory=list)
    route_note: Optional[str] = None


def doi_prefix(doi: str) -> str:
    return normalize_doi(doi).split("/", 1)[0]


def route(doi: str, transport: Transport, cache: Cache,
          throttle: Optional[Throttle] = None, ttl_days: float = 30.0) -> RoutePlan:
    prefix = doi_prefix(doi)
    cached = cache.get("doi_ra", prefix, ttl_days=ttl_days)
    if cached is not None:
        ra = cached.get("ra")
    else:
        try:
            data = transport.get_json(RA_ENDPOINT + prefix, throttle=throttle)
            ra = data[0].get("RA") if isinstance(data, list) and data else None
        except NotFoundError:
            ra = None
        except TransportError as e:
            return RoutePlan(doi_ra="ra_unreachable", sources=list(CONSERVATIVE_SOURCES),
                             route_note=f"注册机构判别端点不可达（{e.code}），回退保守路由")
        cache.put("doi_ra", prefix, {"ra": ra})

    if ra in RA_ROUTES:
        note = ISTIC_NOTE if ra == "ISTIC" else None
        return RoutePlan(doi_ra=ra, sources=list(RA_ROUTES[ra]), route_note=note)
    if ra is None:
        # doi.org/ra/{prefix} 返回 404 或空 → 该前缀未在任一注册机构注册，
        # 是「DOI 不存在」的最强信号（paper-verify 据此径直落 NOT_FOUND，
        # 不在保守路由上浪费重试预算，也防止误判为「查不到但可能存在」）。
        return RoutePlan(doi_ra="not_registered", sources=[],
                         route_note="DOI 前缀未在任一注册机构注册——DOI 不存在的强信号")
    return RoutePlan(doi_ra="unknown", sources=list(CONSERVATIVE_SOURCES),
                     route_note=f"注册机构 {ra} 无专用通路，走保守路由（OpenAlex 收录跨注册机构）")

"""DOI 注册机构（RA）判别与路由计划（spec·第 5 节组件 5）。

带 DOI 条目先分流再查证：Crossref 注册走正常核验；DataCite（含 arXiv
10.48550）经 openalex/arxiv 兜接；中文 DOI（ISTIC / CNKI）走 doi_meta 的
内容协商取题录，取不到则携带「DOI 合法存在、题录待人工核对」标记——防止
Crossref 未命中被误读成编造嫌疑（真实中文文献误伤 = 0 的硬门槛）。
前缀级缓存：同前缀只判一次。

**RA 判别本身就是前缀级存在性证明**：编造的前缀在 doi.org/ra 返回 404 →
not_registered（NOT_FOUND 的最强信号）；能报出注册机构名的前缀是真实注册的。
中文 DOI 因此永不因「查不到题录」被判编造。
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
    # 中文 DOI 两家注册机构都走内容协商（doi_meta）。**不叠加 crossref / openalex**：
    # 它们按定义不收录别家注册的 DOI，加进来只会多两次必然 miss 的请求，还会把
    # 「英文库没有」的 miss 混进中文条目的证据链里，让报告读起来像查无此文。
    "ISTIC": ["doi_meta"],
    "CNKI": ["doi_meta"],
}
CONSERVATIVE_SOURCES = ["crossref", "openalex"]

# 中文 DOI 的注册机构。judge 用它统一走「中文轨绝不进 NOT_FOUND」的出口，
# 新增一家中文 RA 只改这里一处（别处不得另存第二份名单）。
CN_DOI_RA = ("ISTIC", "CNKI")

# 措辞精度（两条 note 都刻意只说「前缀」）：RA 判别是**前缀级**的，前缀注册不证明这一条
# 完整 DOI 存在。实测编造后缀 `10.11821/dlxb209999999` 的前缀照样报 ISTIC，若把 note 写成
# 「DOI 合法存在」，用户读到的就是对一个编造 DOI 的存在性担保——这比不说更糟（不编造底线）。
# 完整 DOI 级的存在性判定要另走 handle API（`hdl.handle.net/api/handles/{doi}`，rc=1 存在 /
# rc=100 不存在），本次不引入。
ISTIC_NOTE = ("ISTIC（中文 DOI）注册：走 DOI 内容协商（doi_meta）取题录；取到即正常核验，"
              "取不到则「前缀已注册、本条题录未取到」，待人工核对，不作编造嫌疑处理")
# 知网自己就是 DOI 注册机构。实测它的内容协商回多重解析 HTML 选择页、不回 CSL-JSON，
# 故 doi_meta 对它多为 miss——但 miss 是这条通路没有，不可读作文献不存在。
CNKI_NOTE = ("CNKI（知网）注册：DOI 前缀已在知网注册；知网未提供内容协商题录，"
             "故题录待人工核对（去知网原始记录核对），不作编造嫌疑处理")


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
        note = {"ISTIC": ISTIC_NOTE, "CNKI": CNKI_NOTE}.get(ra)
        return RoutePlan(doi_ra=ra, sources=list(RA_ROUTES[ra]), route_note=note)
    if ra is None:
        # doi.org/ra/{prefix} 返回 404 或空 → 该前缀未在任一注册机构注册，
        # 是「DOI 不存在」的最强信号（paper-verify 据此径直落 NOT_FOUND，
        # 不在保守路由上浪费重试预算，也防止误判为「查不到但可能存在」）。
        return RoutePlan(doi_ra="not_registered", sources=[],
                         route_note="DOI 前缀未在任一注册机构注册——DOI 不存在的强信号")
    return RoutePlan(doi_ra="unknown", sources=list(CONSERVATIVE_SOURCES),
                     route_note=f"注册机构 {ra} 无专用通路，走保守路由（OpenAlex 收录跨注册机构）")

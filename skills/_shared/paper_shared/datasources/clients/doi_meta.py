"""DOI 内容协商客户端：中文 DOI 的题录来源（ISTIC / CNKI 等非 Crossref 注册机构）。

**为什么有这个源**：此前 routing 断言「ISTIC 未提供免费元数据 API」，把中文 DOI 整源跳过、
径直落待人工核对。这个断言是错的——DOI 全球解析系统本身提供内容协商（content
negotiation）：向 `https://doi.org/{doi}` 带 `Accept: application/vnd.citationstyles.csl+json`
请求，注册机构若支持就直接回 CSL-JSON 题录。实测 `10.11821/dlxb202001001`（《地理学报》）
拿到中文标题、作者、刊名、卷期页与完整中文摘要，字段齐到足以完成核验与笔记表填充。

走的是 DOI 基础设施而非站点接口，因此**不涉及知网 / 万方的 robots.txt 与账号风险**——与
「不把站点 ToS 转嫁给安装者」那条取舍不冲突（见 paper-search/references/知网万方检索方案模板.md）。

**各注册机构支持度不齐，这是本源的核心事实**：
  - ISTIC（中文 DOI 主力）：回 CSL-JSON，题录完整；
  - CNKI（知网自己就是注册机构）：实测回**多重解析 HTML 选择页**、不回 JSON，故本源对它
    是 miss。但 miss 不等于文献不存在——前缀已在知网注册这件事由 routing 的 RA 判别独立
    证明，judge 据此落 PENDING_MANUAL 而非 NOT_FOUND（误伤铁律）。

非 JSON 响应一律按 **miss（该注册机构不支持内容协商）** 处理，不按 error：两者对判定的含义
差着一个「查不成」与「查了没有」，混同会让 CNKI 条目在报告里显示成网络故障。真正的故障
（超时 / 5xx）照常抛 TransportError，如实记 error。

可用性提示：ISTIC 的内容协商实测被 doi.org 代理到自建服务（`122.115.55.36:8000`），稳定性
弱于 Crossref。它不可达时本源返回 error，条目落 UNVERIFIED（查询未完成），不是编造嫌疑。
"""
from __future__ import annotations

import html
import urllib.parse
from typing import Any, Dict, List, Optional

from ..models import SourceHit, normalize_doi
from ..transport import NotFoundError, TransportError
from .base import SourceClient, clean_jats_abstract

# CSL-JSON 的媒体类型。DOI 内容协商由 CrossCite 提供，各 RA 按此 Accept 头回题录。
CSL_JSON_ACCEPT = "application/vnd.citationstyles.csl+json"


def _unescape(value: Optional[str]) -> Optional[str]:
    """反转义 HTML 实体。

    ISTIC 在 CSL-JSON 的文本字段里投递 HTML 实体而非字符——实测标题为
    `理解地理&#x0201C;耦合&#x0201D;实现地理&#x0201C;集成&#x0201D;`。不反转义则用户在
    笔记表与核验报告里看到字面 `&#x0201C;`，且标题比对会因这串噪声而误判为不符。
    """
    if not value or not isinstance(value, str):
        return None
    out = " ".join(html.unescape(value).split())
    return out or None


class DoiMetaClient(SourceClient):
    id = "doi_meta"

    def lookup_doi(self, doi: str) -> Optional[SourceHit]:
        d = normalize_doi(doi)
        # DOI 里的 `/` 必须保留（内容协商的路径就是 `/{prefix}/{suffix}`），只转义空格等
        url = f"{self.config.base_url}/{urllib.parse.quote(d, safe='/')}"
        try:
            data = self._cached_json(f"doi:{d}", url,
                                     headers={"Accept": CSL_JSON_ACCEPT})
        except NotFoundError:
            return None
        except TransportError as e:
            # 非 JSON 响应 = 该注册机构不支持内容协商（CNKI 回 HTML 选择页）→ miss。
            # 其余错误码（TIMEOUT / SERVER_ERROR / RATE_LIMITED）是真故障，照常上抛。
            if e.code == "PARSE_ERROR":
                return None
            raise
        if not isinstance(data, dict) or not data:
            return None
        return self._hit(self._metadata(data), raw=data)

    # ---- 解析 ----

    @staticmethod
    def _metadata(d: Dict[str, Any]) -> Dict[str, Any]:
        """CSL-JSON → 规范化 metadata。字段名是 CSL 规范的，与 Crossref message 不同。"""
        year = None
        parts = ((d.get("issued") or {}).get("date-parts") or [[]])
        if parts and parts[0]:
            first = parts[0][0]
            # ISTIC 实测给整数年；个别 RA 投递字符串，能转就转，转不动留 None（不塞脏值）
            if isinstance(first, int) and not isinstance(first, bool):
                year = first
            elif isinstance(first, str) and first.strip().isdigit():
                year = int(first.strip())
        authors = [n for n in (DoiMetaClient._author_name(a)
                               for a in (d.get("author") or [])) if n]
        return {
            "title": _unescape(DoiMetaClient._first(d.get("title"))),
            "authors": authors,
            "year": year,
            "venue": _unescape(DoiMetaClient._first(d.get("container-title"))),
            "doi": normalize_doi(d.get("DOI") or "") or None,
            "type": d.get("type"),
            # CSL-JSON 不含被引数——留 None（未知），不补 0（「零被引」≠「该源不给这个数」）
            "cited_by_count": None,
            # ISTIC 的 abstract 是 HTML 片段（`<p id="C2">…</p>` + 实体），与 Crossref 的
            # JATS 片段同构，故复用同一个清洗器：剥标签 + 反转义 + 剥不干净则返回 None。
            "abstract": clean_jats_abstract(d.get("abstract")),
            # 内容协商不提供 ORCID 与机构，如实给空（不造空壳，见 author_details_or_empty）
            "author_details": [],
        }

    @staticmethod
    def _first(value: Any) -> Optional[str]:
        """CSL 的 title / container-title 多为字符串，个别 RA 投数组——两种都收。"""
        if isinstance(value, str):
            return value
        if isinstance(value, list) and value:
            return value[0] if isinstance(value[0], str) else None
        return None

    @staticmethod
    def _author_name(a: Any) -> Optional[str]:
        """CSL 作者 → 姓名字符串。

        中文作者实测整名落在 `given`（`{"given": "宋长青"}`，无 family），所以拼接必须容忍
        任一侧缺失；`literal` 是机构 / 团体作者的专用字段（CSL 规范），一并认。
        """
        if not isinstance(a, dict):
            return None
        lit = _unescape(a.get("literal"))
        if lit:
            return lit
        parts = [_unescape(a.get("given")), _unescape(a.get("family"))]
        return " ".join(p for p in parts if p) or None

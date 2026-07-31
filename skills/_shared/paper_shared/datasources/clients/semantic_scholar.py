"""Semantic Scholar 客户端：无 key 走 1 req/s 慢速档（probe 报 partial）。"""
from __future__ import annotations

import urllib.parse
from typing import Any, Dict, List, Optional

from ..models import ProbeResult, SourceHit, normalize_doi
from ..transport import NotFoundError
from .base import SourceClient, TYPE_MAP

_FIELDS = "title,authors,year,venue,externalIds,publicationTypes,citationCount,abstract"

# 缓存键的 fields 版本段。**改 _FIELDS 必须同步改这个值。**
#
# 本类的缓存键（`doi:` / `match:` / `_search_cache_key`）都只由 DOI / 题名 / limit / filters
# 组成，**不含 fields**——而 fields 是 URL 的一部分。所以扩了 _FIELDS 却不动键，7 天 TTL
# 内的旧缓存会照命中，返回的是按老字段集取回的 payload：新字段一律缺失，用户看到的是
# 「一部分条目有被引数、一部分没有」，且从检索结果里看不出原因。
# 换个版本段等于让老键自然作废。缓存是性能设施不是证据（见 cache.py 模块注释），失效可接受。
_FIELDS_VER = "f2"


class SemanticScholarClient(SourceClient):
    id = "semantic_scholar"

    def _headers(self) -> Dict[str, str]:
        return {"x-api-key": self.api_key} if self.api_key else {}

    @staticmethod
    def _versioned(key: str) -> str:
        """给缓存键缀上 fields 版本段（理由见 _FIELDS_VER）。"""
        return f"{key}:{_FIELDS_VER}"

    def lookup_doi(self, doi: str) -> Optional[SourceHit]:
        d = normalize_doi(doi)
        url = (f"{self.config.base_url}/graph/v1/paper/DOI:"
               f"{urllib.parse.quote(d, safe='/.')}?fields={_FIELDS}")
        try:
            data = self._cached_json(self._versioned(f"doi:{d}"), url,
                                     headers=self._headers())
        except NotFoundError:
            return None
        return self._hit(self._metadata(data), raw=self._trim(data))

    def match(self, title: str, authors: Optional[List[str]] = None,
              year: Optional[int] = None, limit: int = 5) -> List[SourceHit]:
        q = urllib.parse.quote(title)
        url = f"{self.config.base_url}/graph/v1/paper/search?query={q}&limit={limit}&fields={_FIELDS}"
        try:
            data = self._cached_json(self._versioned(f"match:{title.lower()}:{limit}"), url,
                                     headers=self._headers())
        except NotFoundError:
            return []
        return [self._hit(self._metadata(p), raw=self._trim(p))
                for p in data.get("data") or []]

    def search(self, query: str, filters: Optional[Dict[str, Any]] = None,
               limit: int = 20) -> List[SourceHit]:
        if not filters:
            return self.match(query, limit=limit)   # filters 空：与既有逐字节一致（走 match 缓存键）
        q = urllib.parse.quote(query)
        url = (f"{self.config.base_url}/graph/v1/paper/search?query={q}"
               f"&limit={limit}&fields={_FIELDS}{self._filter_param(filters)}")
        try:
            data = self._cached_json(
                self._versioned(self._search_cache_key(query, limit, filters)), url,
                headers=self._headers())
        except NotFoundError:
            return []
        hits = [self._hit(self._metadata(p), raw=self._trim(p)) for p in data.get("data") or []]
        return self._postfilter(hits, filters)

    @staticmethod
    def _filter_param(filters: Dict[str, Any]) -> str:
        """S2 检索过滤：year 区间（{lo}-{hi}）+ publicationTypes。"""
        parts: List[str] = []
        yf, yt = filters.get("year_from"), filters.get("year_to")
        if yf is not None or yt is not None:
            lo = yf if yf is not None else ""
            hi = yt if yt is not None else ""
            parts.append(f"&year={lo}-{hi}")
        typ = filters.get("type")
        if typ and TYPE_MAP["semantic_scholar"].get(typ):
            parts.append(f"&publicationTypes={TYPE_MAP['semantic_scholar'][typ]}")
        return "".join(parts)

    # ---- 滚雪球（capabilities: references / cited_by）----

    def _snowball(self, doi: str, edge: str, payload_key: str, limit: int) -> List[SourceHit]:
        """S2 的两向共用一条路径：`/paper/DOI:{doi}/{edge}` 一次调用直接回题录。

        响应形如 `{"data": [{"citedPaper": {...}}, ...]}`——每条是一个**边**对象，题录裹在
        `citedPaper`（后向）或 `citingPaper`（前向）里，要剥一层才是 paper。
        S2 的 limit 上限 1000，超了它自己会报 400，故此处夹住。
        """
        d = normalize_doi(doi)
        capped = max(1, min(int(limit), 1000))
        url = (f"{self.config.base_url}/graph/v1/paper/DOI:"
               f"{urllib.parse.quote(d, safe='/.')}/{edge}"
               f"?fields={_FIELDS}&limit={capped}")
        try:
            data = self._cached_json(self._versioned(f"{edge}:{d}:{capped}"), url,
                                     headers=self._headers())
        except NotFoundError:
            return []
        out: List[SourceHit] = []
        for row in data.get("data") or []:
            paper = (row or {}).get(payload_key) or {}
            # S2 对已知存在但未收录元数据的边会回 {"citedPaper": {"paperId": null}}——
            # 无题名的条目进表只是一行空白，跳过。
            if paper.get("title"):
                out.append(self._hit(self._metadata(paper), raw=self._trim(paper)))
        return out

    def references(self, doi: str, limit: int = 50) -> List[SourceHit]:
        return self._snowball(doi, "references", "citedPaper", limit)

    def cited_by(self, doi: str, limit: int = 50) -> List[SourceHit]:
        return self._snowball(doi, "citations", "citingPaper", limit)

    def probe(self) -> ProbeResult:
        result = super().probe()
        if result.status == "ok" and not self.api_key:
            return ProbeResult(source=self.id, status="partial", role=self.config.role,
                               reason="未配置 API key（SEMANTIC_SCHOLAR_API_KEY），走 1 req/s 慢速档")
        return result

    @staticmethod
    def _metadata(p: Dict[str, Any]) -> Dict[str, Any]:
        ext = p.get("externalIds") or {}
        types = p.get("publicationTypes") or []
        return {"title": p.get("title"),
                "authors": [a.get("name") for a in (p.get("authors") or []) if a.get("name")],
                "year": p.get("year"), "venue": p.get("venue") or None,
                "doi": normalize_doi(ext["DOI"]) if ext.get("DOI") else None,
                "type": types[0] if types else None,
                # 源没给就是 None，不补 0（「零被引」≠「该源不给这个数」）
                "cited_by_count": p.get("citationCount"),
                "abstract": p.get("abstract") or None}

    @staticmethod
    def _trim(p: Dict[str, Any]) -> Dict[str, Any]:
        # abstract 不进 raw：全文级体积，还原后的文本已在 metadata.abstract（同 openalex）
        keep = ("paperId", "title", "year", "venue", "externalIds", "authors",
                "publicationTypes", "citationCount")
        return {k: p[k] for k in keep if k in p}

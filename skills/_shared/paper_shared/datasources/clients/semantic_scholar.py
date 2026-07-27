"""Semantic Scholar 客户端：无 key 走 1 req/s 慢速档（probe 报 partial）。"""
from __future__ import annotations

import urllib.parse
from typing import Any, Dict, List, Optional

from ..models import ProbeResult, SourceHit, normalize_doi
from ..transport import NotFoundError
from .base import SourceClient, TYPE_MAP

_FIELDS = "title,authors,year,venue,externalIds,publicationTypes"


class SemanticScholarClient(SourceClient):
    id = "semantic_scholar"

    def _headers(self) -> Dict[str, str]:
        return {"x-api-key": self.api_key} if self.api_key else {}

    def lookup_doi(self, doi: str) -> Optional[SourceHit]:
        d = normalize_doi(doi)
        url = (f"{self.config.base_url}/graph/v1/paper/DOI:"
               f"{urllib.parse.quote(d, safe='/.')}?fields={_FIELDS}")
        try:
            data = self._cached_json(f"doi:{d}", url, headers=self._headers())
        except NotFoundError:
            return None
        return self._hit(self._metadata(data), raw=self._trim(data))

    def match(self, title: str, authors: Optional[List[str]] = None,
              year: Optional[int] = None, limit: int = 5) -> List[SourceHit]:
        q = urllib.parse.quote(title)
        url = f"{self.config.base_url}/graph/v1/paper/search?query={q}&limit={limit}&fields={_FIELDS}"
        try:
            data = self._cached_json(f"match:{title.lower()}:{limit}", url,
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
            data = self._cached_json(self._search_cache_key(query, limit, filters), url,
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
                "type": types[0] if types else None}

    @staticmethod
    def _trim(p: Dict[str, Any]) -> Dict[str, Any]:
        keep = ("paperId", "title", "year", "venue", "externalIds", "authors",
                "publicationTypes")
        return {k: p[k] for k in keep if k in p}

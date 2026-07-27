"""OpenAlex 客户端：跨注册机构的免费全学科元数据。"""
from __future__ import annotations

import urllib.parse
from typing import Any, Dict, List, Optional

from ..models import SourceHit, normalize_doi
from ..transport import NotFoundError
from .base import SourceClient, TYPE_MAP


class OpenAlexClient(SourceClient):
    id = "openalex"

    def lookup_doi(self, doi: str) -> Optional[SourceHit]:
        d = normalize_doi(doi)
        url = f"{self.config.base_url}/works/doi:{urllib.parse.quote(d, safe='/.')}"
        try:
            data = self._cached_json(f"doi:{d}", url)
        except NotFoundError:
            return None
        return self._hit(self._metadata(data), raw=self._trim(data))

    def match(self, title: str, authors: Optional[List[str]] = None,
              year: Optional[int] = None, limit: int = 5) -> List[SourceHit]:
        q = urllib.parse.quote(title)
        url = f"{self.config.base_url}/works?filter=title.search:{q}&per-page={limit}"
        try:
            data = self._cached_json(f"match:{title.lower()}:{limit}", url)
        except NotFoundError:
            return []
        return [self._hit(self._metadata(w), raw=self._trim(w))
                for w in data.get("results") or []]

    def search(self, query: str, filters: Optional[Dict[str, Any]] = None,
               limit: int = 20) -> List[SourceHit]:
        q = urllib.parse.quote(query)
        url = f"{self.config.base_url}/works?search={q}&per-page={limit}{self._filter_param(filters)}"
        try:
            data = self._cached_json(self._search_cache_key(query, limit, filters), url)
        except NotFoundError:
            return []
        hits = [self._hit(self._metadata(w), raw=self._trim(w))
                for w in data.get("results") or []]
        return self._postfilter(hits, filters)

    @staticmethod
    def _filter_param(filters: Optional[Dict[str, Any]]) -> str:
        """OpenAlex filter 段：from/to_publication_date / type。与 search= 参数并存。filters 空 → 空串。"""
        if not filters:
            return ""
        parts: List[str] = []
        yf, yt = filters.get("year_from"), filters.get("year_to")
        if yf is not None:
            parts.append(f"from_publication_date:{yf}-01-01")
        if yt is not None:
            parts.append(f"to_publication_date:{yt}-12-31")
        typ = filters.get("type")
        if typ and TYPE_MAP["openalex"].get(typ):
            parts.append(f"type:{TYPE_MAP['openalex'][typ]}")
        if not parts:
            return ""
        return "&filter=" + urllib.parse.quote(",".join(parts), safe=":,-_")

    @staticmethod
    def _metadata(w: Dict[str, Any]) -> Dict[str, Any]:
        doi = w.get("doi")
        venue = ((w.get("primary_location") or {}).get("source") or {}).get("display_name")
        return {"title": w.get("display_name"),
                "authors": [((a.get("author") or {}).get("display_name"))
                            for a in (w.get("authorships") or [])
                            if (a.get("author") or {}).get("display_name")],
                "year": w.get("publication_year"),
                "venue": venue,
                "doi": normalize_doi(doi) if doi else None,
                "type": w.get("type")}

    @staticmethod
    def _trim(w: Dict[str, Any]) -> Dict[str, Any]:
        keep = ("id", "doi", "display_name", "publication_year", "type",
                "authorships", "primary_location")
        return {k: w[k] for k in keep if k in w}

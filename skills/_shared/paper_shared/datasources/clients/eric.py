"""ERIC 客户端：教育学学科补充源（无 lookup_doi 能力，只有 search/match）。"""
from __future__ import annotations

import urllib.parse
from typing import Any, Dict, List, Optional

from ..models import SourceHit, normalize_doi
from ..transport import NotFoundError
from .base import SourceClient


class EricClient(SourceClient):
    id = "eric"

    def match(self, title: str, authors: Optional[List[str]] = None,
              year: Optional[int] = None, limit: int = 5) -> List[SourceHit]:
        return self.search(title, limit=limit)

    def search(self, query: str, filters: Optional[Dict[str, Any]] = None,
               limit: int = 20) -> List[SourceHit]:
        q = urllib.parse.quote(query)
        url = f"{self.config.base_url}/?search={q}&format=json&rows={limit}"
        try:
            data = self._cached_json(f"search:{query.lower()}:{limit}", url)
        except NotFoundError:
            return []
        docs = ((data.get("response") or {}).get("docs")) or []
        hits = [self._hit(self._metadata(d), raw=d) for d in docs]
        return self._postfilter(hits, filters)   # ERIC 无稳定原生年份过滤，靠客户端侧兜底

    @staticmethod
    def _metadata(doc: Dict[str, Any]) -> Dict[str, Any]:
        types = doc.get("publicationtype") or []
        return {"title": doc.get("title"),
                "authors": list(doc.get("author") or []),
                "year": doc.get("publicationdateyear"),
                "venue": doc.get("publication"),
                "doi": normalize_doi(doc["doi"]) if doc.get("doi") else None,
                "type": types[0] if types else None}

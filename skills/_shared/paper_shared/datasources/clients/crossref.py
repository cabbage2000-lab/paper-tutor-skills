"""Crossref 客户端：DOI 元数据 + 内置 Retraction Watch 撤稿数据（update-to）。"""
from __future__ import annotations

import urllib.parse
from typing import Any, Dict, List, Optional

from ..models import SourceHit, normalize_doi
from ..transport import NotFoundError
from .base import SourceClient, TYPE_MAP


class CrossrefClient(SourceClient):
    id = "crossref"

    def lookup_doi(self, doi: str) -> Optional[SourceHit]:
        d = normalize_doi(doi)
        url = f"{self.config.base_url}/works/{urllib.parse.quote(d, safe='')}"
        try:
            data = self._cached_json(f"doi:{d}", url)
        except NotFoundError:
            return None
        msg = data.get("message") or {}
        return self._hit(self._metadata(msg), raw=msg, retraction=self._retraction(msg))

    def match(self, title: str, authors: Optional[List[str]] = None,
              year: Optional[int] = None, limit: int = 5) -> List[SourceHit]:
        q = urllib.parse.quote(title)
        url = f"{self.config.base_url}/works?query.bibliographic={q}&rows={limit}"
        try:
            data = self._cached_json(f"match:{title.lower()}:{limit}", url)
        except NotFoundError:
            return []
        items = (data.get("message") or {}).get("items") or []
        return [self._hit(self._metadata(m), raw=m, retraction=self._retraction(m))
                for m in items]

    def search(self, query: str, filters: Optional[Dict[str, Any]] = None,
               limit: int = 20) -> List[SourceHit]:
        q = urllib.parse.quote(query)
        url = f"{self.config.base_url}/works?query={q}&rows={limit}{self._filter_param(filters)}"
        try:
            data = self._cached_json(self._search_cache_key(query, limit, filters), url)
        except NotFoundError:
            return []
        items = (data.get("message") or {}).get("items") or []
        hits = [self._hit(self._metadata(m), raw=m, retraction=self._retraction(m))
                for m in items]
        return self._postfilter(hits, filters)

    @staticmethod
    def _filter_param(filters: Optional[Dict[str, Any]]) -> str:
        """Crossref filter 段：from-pub-date / until-pub-date / type（逗号分隔）。filters 空 → 空串。"""
        if not filters:
            return ""
        parts: List[str] = []
        yf, yt = filters.get("year_from"), filters.get("year_to")
        if yf is not None:
            parts.append(f"from-pub-date:{yf}-01-01")
        if yt is not None:
            parts.append(f"until-pub-date:{yt}-12-31")
        typ = filters.get("type")
        if typ and TYPE_MAP["crossref"].get(typ):
            parts.append(f"type:{TYPE_MAP['crossref'][typ]}")
        if not parts:
            return ""
        return "&filter=" + urllib.parse.quote(",".join(parts), safe=":,-")

    # ---- 解析 ----

    @staticmethod
    def _metadata(msg: Dict[str, Any]) -> Dict[str, Any]:
        titles = msg.get("title") or []
        authors = [" ".join(x for x in (a.get("given"), a.get("family")) if x)
                   for a in (msg.get("author") or [])]
        year = None
        parts = ((msg.get("issued") or {}).get("date-parts") or [[]])
        if parts and parts[0]:
            year = parts[0][0]
        containers = msg.get("container-title") or []
        return {"title": titles[0] if titles else None, "authors": authors, "year": year,
                "venue": containers[0] if containers else None,
                "doi": normalize_doi(msg.get("DOI", "")) or None, "type": msg.get("type")}

    @staticmethod
    def _retraction(msg: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        for upd in msg.get("update-to") or []:
            label = f"{upd.get('type', '')} {upd.get('label', '')}".lower()
            if "retract" in label:
                return {"type": "retraction", "label": upd.get("label"),
                        "date_parts": (upd.get("updated") or {}).get("date-parts"),
                        "doi": upd.get("DOI")}
        return None

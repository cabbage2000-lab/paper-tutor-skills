"""arXiv 客户端：Atom XML 解析 + DataCite DOI（10.48550/arXiv.<id>）转 arXiv ID。

arXiv API 礼仪要求 ≥ 3s 间隔（注册表已声明），由 batch 引擎在源内串行节流。
"""
from __future__ import annotations

import urllib.parse
import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional

from ..models import SourceHit, normalize_doi
from ..transport import NotFoundError
from .base import SourceClient

_ATOM_NS = "http://www.w3.org/2005/Atom"
_ARXIV_NS = "http://arxiv.org/schemas/atom"
_DATACITE_PREFIX = "10.48550"


class ArxivClient(SourceClient):
    id = "arxiv"

    @staticmethod
    def doi_to_arxiv_id(doi: str) -> Optional[str]:
        d = normalize_doi(doi)
        prefix = d.split("/", 1)[0]
        if prefix != _DATACITE_PREFIX:
            return None
        rest = d.split("/", 1)[1] if "/" in d else ""
        for sep in ("arxiv.", "arxiv:"):
            idx = rest.lower().find(sep)
            if idx != -1:
                return rest[idx + len(sep):]
        return rest or None

    def lookup_arxiv_id(self, arxiv_id: str) -> Optional[SourceHit]:
        url = (f"{self.config.base_url}/query?id_list={urllib.parse.quote(arxiv_id)}"
               f"&max_results=1")
        try:
            text = self._cached_text(f"arxiv_id:{arxiv_id}", url)
        except NotFoundError:
            return None
        entries = self._parse_entries(text)
        if not entries:
            return None
        return self._hit_from_entry(entries[0])

    def lookup_doi(self, doi: str) -> Optional[SourceHit]:
        aid = self.doi_to_arxiv_id(doi)
        if aid is None:
            return None
        return self.lookup_arxiv_id(aid)

    def match(self, title: str, authors: Optional[List[str]] = None,
              year: Optional[int] = None, limit: int = 5) -> List[SourceHit]:
        q = urllib.parse.quote(title)
        url = f"{self.config.base_url}/query?search_query=ti:{q}&max_results={limit}"
        try:
            text = self._cached_text(f"match:{title.lower()}:{limit}", url)
        except NotFoundError:
            return []
        return [self._hit_from_entry(e) for e in self._parse_entries(text)]

    def search(self, query: str, filters: Optional[Dict[str, Any]] = None,
               limit: int = 20) -> List[SourceHit]:
        q = urllib.parse.quote(query)
        url = f"{self.config.base_url}/query?search_query=all:{q}&max_results={limit}"
        try:
            text = self._cached_text(f"search:{query.lower()}:{limit}", url)
        except NotFoundError:
            return []
        hits = [self._hit_from_entry(e) for e in self._parse_entries(text)]
        return self._postfilter(hits, filters)   # arxiv 无原生 year/type 过滤，靠客户端侧兜底

    # ---- Atom 解析 ----

    def _cached_text(self, key: str, url: str) -> str:
        """缓存文本（Atom），与 base._cached_json 同构但不经 json.loads。"""
        ttl = self.config.cache_ttl_days or 7
        if not self.fresh:
            cached = self.cache.get(self.id, key, ttl_days=ttl)
            if cached is not None:
                self._last_from_cache = True
                return cached.get("_text", "")
        self._last_from_cache = False
        text = self.transport.get_text(url, throttle=self.throttle)
        self.cache.put(self.id, key, {"_text": text})
        return text

    def _parse_entries(self, xml_text: str) -> List[ET.Element]:
        root = ET.fromstring(xml_text)
        return list(root.findall(f"{{{_ATOM_NS}}}entry"))

    def _hit_from_entry(self, entry: ET.Element) -> SourceHit:
        raw = self._entry_to_dict(entry)
        return self._hit(self._metadata(raw), raw=raw)

    @staticmethod
    def _entry_to_dict(entry: ET.Element) -> Dict[str, Any]:
        def _text(tag: str) -> Optional[str]:
            el = entry.find(f"{{{_ATOM_NS}}}{tag}")
            return el.text.strip() if el is not None and el.text else None

        authors = []
        for au in entry.findall(f"{{{_ATOM_NS}}}author"):
            name_el = au.find(f"{{{_ATOM_NS}}}name")
            if name_el is not None and name_el.text:
                authors.append(name_el.text.strip())

        arxiv_id_full = _text("id") or ""
        # http://arxiv.org/abs/1706.03762v5 → 1706.03762
        short = arxiv_id_full.rstrip("/").split("/abs/")[-1]
        short = short.split("v")[0]

        doi_el = entry.find(f"{{{_ARXIV_NS}}}doi")
        doi = doi_el.text.strip() if doi_el is not None and doi_el.text else None

        published = _text("published") or ""
        year = int(published[:4]) if len(published) >= 4 and published[:4].isdigit() else None

        cat_el = entry.find(f"{{{_ARXIV_NS}}}primary_category")
        category = cat_el.get("term") if cat_el is not None else None

        return {"id": short, "full_id": arxiv_id_full, "title": _text("title"),
                "authors": authors, "published": published, "year": year,
                "doi": normalize_doi(doi) if doi else None,
                "category": category}

    @staticmethod
    def _metadata(raw: Dict[str, Any]) -> Dict[str, Any]:
        return {"title": raw.get("title"), "authors": raw.get("authors") or [],
                "year": raw.get("year"), "venue": None,
                "doi": raw.get("doi"), "type": "preprint"}

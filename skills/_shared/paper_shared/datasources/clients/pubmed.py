"""PubMed 客户端（E-utilities esummary）：医学学科补充源。

PubMed 的 DOI 查询分两步（esearch 得 UID → esummary 得元数据），这里简化为
用 esummary 的 DOI 过滤模式直接查（实际实现时冒烟验证端点，可改回两步）。
"""
from __future__ import annotations

import urllib.parse
from typing import Any, Dict, List, Optional

from ..models import SourceHit, normalize_doi
from ..transport import NotFoundError
from .base import SourceClient


class PubMedClient(SourceClient):
    id = "pubmed"

    def _key_param(self) -> str:
        return f"&api_key={self.api_key}" if self.api_key else ""

    def _lookup_uid(self, doi: str) -> Optional[str]:
        d = normalize_doi(doi)
        url = (f"{self.config.base_url}/esearch.fcgi?db=pubmed&term={d}[doi]"
               f"&retmode=json&retmax=1{self._key_param()}")
        try:
            data = self._cached_json(f"esearch:{d}", url)
        except NotFoundError:
            return None
        ids = (data.get("esearchresult") or {}).get("idlist") or []
        return ids[0] if ids else None

    def lookup_doi(self, doi: str) -> Optional[SourceHit]:
        d = normalize_doi(doi)
        uid = self._lookup_uid(d)
        if uid is None:
            return None
        url = (f"{self.config.base_url}/esummary.fcgi?db=pubmed&id={uid}"
               f"&retmode=json{self._key_param()}")
        try:
            data = self._cached_json(f"esummary:{uid}", url)
        except NotFoundError:
            return None
        doc = (data.get("result") or {}).get(uid)
        if not doc:
            return None
        return self._hit(self._metadata(doc), raw=doc)

    def match(self, title: str, authors: Optional[List[str]] = None,
              year: Optional[int] = None, limit: int = 5) -> List[SourceHit]:
        q = urllib.parse.quote(title)
        url = (f"{self.config.base_url}/esearch.fcgi?db=pubmed&term={q}"
               f"&retmode=json&retmax={limit}{self._key_param()}")
        try:
            data = self._cached_json(f"match:{title.lower()}:{limit}", url)
        except NotFoundError:
            return []
        uids = (data.get("esearchresult") or {}).get("idlist") or []
        if not uids:
            return []
        sum_url = (f"{self.config.base_url}/esummary.fcgi?db=pubmed"
                   f"&id={','.join(uids)}&retmode=json{self._key_param()}")
        try:
            sdata = self._cached_json(f"esummary:batch:{','.join(uids)}", sum_url)
        except NotFoundError:
            return []
        result = sdata.get("result") or {}
        hits = []
        for uid in uids:
            doc = result.get(uid)
            if doc:
                hits.append(self._hit(self._metadata(doc), raw=doc))
        return hits

    def search(self, query: str, filters: Optional[Dict[str, Any]] = None,
               limit: int = 20) -> List[SourceHit]:
        # 补充源：filters 空时与既有逐字节一致；非空时靠客户端侧兜底过滤（缓存原始 match 结果、
        # 过滤在读缓存之后，不串味）。year 用数字比较可靠，type 依赖 pubtype 归一。
        return self._postfilter(self.match(query, limit=limit), filters)

    @staticmethod
    def _metadata(doc: Dict[str, Any]) -> Dict[str, Any]:
        pubdate = doc.get("pubdate") or ""
        year = int(pubdate[:4]) if len(pubdate) >= 4 and pubdate[:4].isdigit() else None
        doi = None
        for aid in doc.get("articleids") or []:
            if aid.get("idtype") == "doi" and aid.get("value"):
                doi = normalize_doi(aid["value"])
                break
        types = doc.get("pubtype") or []
        return {"title": doc.get("title"),
                "authors": [a.get("name") for a in (doc.get("authors") or []) if a.get("name")],
                "year": year, "venue": doc.get("fulljournalname"),
                "doi": doi, "type": types[0] if types else None}

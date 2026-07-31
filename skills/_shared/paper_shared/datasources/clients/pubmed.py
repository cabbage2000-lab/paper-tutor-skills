"""PubMed 客户端（E-utilities esummary）：医学学科补充源。

PubMed 的 DOI 查询分两步（esearch 得 UID → esummary 得元数据），这里简化为
用 esummary 的 DOI 过滤模式直接查（实际实现时冒烟验证端点，可改回两步）。
"""
from __future__ import annotations

import urllib.parse
import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional

from ..models import SourceHit, normalize_doi
from ..transport import NotFoundError, TransportError
from .base import SourceClient


class PubMedClient(SourceClient):
    id = "pubmed"

    def _key_param(self) -> str:
        return f"&api_key={self.api_key}" if self.api_key else ""

    # ---- 摘要（efetch）----

    def _fetch_abstracts(self, uids: List[str]) -> Dict[str, str]:
        """批量取摘要。**esummary 不返回摘要**，必须另走 efetch（XML）——这是 PubMed 与
        其他源的结构性差异，不是能省的一次调用。

        与 esummary 同一批 uid，一次往返；失败一律吞掉返回空字典：题录此时已经拿到，
        为了摘要把整源判成「未覆盖（网络故障）」是把次要字段的失败升级成主要能力的失败。
        摘要缺失在笔记表里如实显示为「无摘要，未起草」（见 SKILL.md 起草档）。
        """
        if not uids:
            return {}
        joined = ",".join(uids)
        url = (f"{self.config.base_url}/efetch.fcgi?db=pubmed&id={joined}"
               f"&retmode=xml{self._key_param()}")
        # 摘要是附属调用，不该改写主查询（esummary）的缓存命中标记——否则 stats 的
        # cache_hit_rate 报的是最后一次 HTTP 的状态，不是这批题录的来源。存了再还。
        main_from_cache = self._last_from_cache
        try:
            data = self._cached_json(f"efetch:abs:{joined}", url)
            return self._parse_abstracts(data.get("_text") or "")
        except (NotFoundError, TransportError):
            return {}
        finally:
            self._last_from_cache = main_from_cache

    def _cached_json(self, key: str, url: str,
                     headers: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        """efetch 返回 XML 而非 JSON，故对 `efetch:` 键改走文本通道、包一层 `{"_text": ...}`
        （同 arxiv 的 `_cached_text` 手法）。其余键沿用基类的 JSON 通道。"""
        if not key.startswith("efetch:"):
            return super()._cached_json(key, url, headers=headers)
        ttl = self.config.cache_ttl_days or 7
        if not self.fresh:
            cached = self.cache.get(self.id, key, ttl_days=ttl)
            if cached is not None:
                self._last_from_cache = True
                return cached
        self._last_from_cache = False
        payload = {"_text": self.transport.get_text(url, headers=headers,
                                                    throttle=self.throttle)}
        self.cache.put(self.id, key, payload)
        return payload

    @staticmethod
    def _parse_abstracts(xml_text: str) -> Dict[str, str]:
        """efetch XML → {uid: 摘要}。结构化摘要（多个带 Label 的 AbstractText）按
        `LABEL: 正文` 逐段拼接——丢掉 Label 会让「方法」「结论」几段糊成一团。
        解析失败返回空字典，不抛（摘要是可选字段，见 _fetch_abstracts）。"""
        if not xml_text.strip():
            return {}
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError:
            return {}
        out: Dict[str, str] = {}
        for art in root.iter("PubmedArticle"):
            cit = art.find("MedlineCitation")
            if cit is None:
                continue
            pmid_el = cit.find("PMID")
            if pmid_el is None or not (pmid_el.text or "").strip():
                continue
            parts: List[str] = []
            for node in cit.iter("AbstractText"):
                # itertext() 而非 .text：AbstractText 里可能嵌 <i>/<sup> 等标签，
                # 只取 .text 会在第一个子标签处截断，把摘要砍掉半句。
                body = " ".join("".join(node.itertext()).split())
                if not body:
                    continue
                label = (node.get("Label") or node.get("NlmCategory") or "").strip()
                parts.append(f"{label}: {body}" if label else body)
            if parts:
                out[pmid_el.text.strip()] = " ".join(parts)
        return out

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
        abstracts = self._fetch_abstracts([uid])
        return self._hit(self._metadata(doc, abstracts.get(uid)), raw=doc)

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
        abstracts = self._fetch_abstracts(uids)
        hits = []
        for uid in uids:
            doc = result.get(uid)
            if doc:
                hits.append(self._hit(self._metadata(doc, abstracts.get(uid)), raw=doc))
        return hits

    def search(self, query: str, filters: Optional[Dict[str, Any]] = None,
               limit: int = 20) -> List[SourceHit]:
        # 补充源：filters 空时与既有逐字节一致；非空时靠客户端侧兜底过滤（缓存原始 match 结果、
        # 过滤在读缓存之后，不串味）。year 用数字比较可靠，type 依赖 pubtype 归一。
        return self._postfilter(self.match(query, limit=limit), filters)

    @staticmethod
    def _metadata(doc: Dict[str, Any], abstract: Optional[str] = None) -> Dict[str, Any]:
        pubdate = doc.get("pubdate") or ""
        year = int(pubdate[:4]) if len(pubdate) >= 4 and pubdate[:4].isdigit() else None
        doi = None
        for aid in doc.get("articleids") or []:
            if aid.get("idtype") == "doi" and aid.get("value"):
                doi = normalize_doi(aid["value"])
                break
        types = doc.get("pubtype") or []
        # cited_by_count 有意不设键：E-utilities 不给被引数，设成 0 会把「未知」说成「零被引」。
        return {"title": doc.get("title"),
                "authors": [a.get("name") for a in (doc.get("authors") or []) if a.get("name")],
                "year": year, "venue": doc.get("fulljournalname"),
                "doi": doi, "type": types[0] if types else None,
                "abstract": abstract}

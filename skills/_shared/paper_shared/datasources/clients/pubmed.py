"""PubMed 客户端（E-utilities esummary）：医学学科补充源。

PubMed 的 DOI 查询分两步（esearch 得 UID → esummary 得元数据），这里简化为
用 esummary 的 DOI 过滤模式直接查（实际实现时冒烟验证端点，可改回两步）。
"""
from __future__ import annotations

import re
import urllib.parse
import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional, Tuple

from ..models import SourceHit, normalize_doi
from ..transport import NotFoundError, TransportError
from .base import SourceClient, oa_record

# PMC 文章落地页。2026-08-04 实测：旧写法 `www.ncbi.nlm.nih.gov/pmc/articles/…` 回 301
# 跳到这个域，故直接用目的地（少一跳，也不给用户一个必然重定向的链接）。
_PMC_ARTICLE_URL = "https://pmc.ncbi.nlm.nih.gov/articles/{}/"

# esummary 的 pubtype 数组里表示「本文已被撤稿」的取值（MeSH 出版类型 D016441）。
_RETRACTED_PUBTYPE = "retracted publication"

# 撤稿 / 关注声明的 RefSource 里的 DOI，形如
# `Vet Res Commun. 2026 Jul 27;50(5):485. doi: 10.1007/s11259-026-11432-9.`
# 句末的句点不属于 DOI，故字符类排掉常见句读；分号是卷期页分隔符，也要排。
_REFSOURCE_DOI = re.compile(r"\bdoi:\s*(10\.[^\s;]+)", re.I)
_DOI_TRAILING = ".,;:)]"

# CommentsCorrections 的 RefType。**方向不能读反**：`…In` 才是「本文被撤稿 / 被关注」，
# `…Of` 是「本文就是那份声明」（极罕见）。与 crossref.py 的 update-to / updated-by 同一个
# 坑——读反则撤稿态永不触发。
_REFTYPE_RETRACTION_IN = "RetractionIn"
_REFTYPE_EOC_IN = "ExpressionOfConcernIn"


class PubMedClient(SourceClient):
    id = "pubmed"

    def _key_param(self) -> str:
        return f"&api_key={self.api_key}" if self.api_key else ""

    # ---- 摘要与撤稿详情（efetch）----

    def _fetch_details(self, uids: List[str]) -> Tuple[Dict[str, str],
                                                       Dict[str, Dict[str, Any]]]:
        """批量取摘要**与撤稿 / 关注声明详情**，返回 `(摘要, 声明)` 两张按 uid 索引的表。

        **esummary 不返回摘要**，必须另走 efetch（XML）——这是 PubMed 与其他源的结构性
        差异，不是能省的一次调用。撤稿详情就在同一份 XML 里（`CommentsCorrections`），
        所以搭这趟车是**零额外请求**：与 esummary 同一批 uid，一次往返。

        失败一律吞掉返回两个空字典：题录此时已经拿到，为了附属字段把整源判成
        「未覆盖（网络故障）」是把次要字段的失败升级成主要能力的失败。摘要缺失在笔记表里
        如实显示为「无摘要，未起草」（见 SKILL.md 起草档）；撤稿详情缺失也不影响撤稿标记
        本身——esummary 的 `pubtype` 快路径已经拿到撤稿事实（见 `_retraction`）。
        """
        if not uids:
            return {}, {}
        joined = ",".join(uids)
        url = (f"{self.config.base_url}/efetch.fcgi?db=pubmed&id={joined}"
               f"&retmode=xml{self._key_param()}")
        # 附属调用不该改写主查询（esummary）的缓存命中标记——否则 stats 的
        # cache_hit_rate 报的是最后一次 HTTP 的状态，不是这批题录的来源。存了再还。
        main_from_cache = self._last_from_cache
        try:
            data = self._cached_json(f"efetch:abs:{joined}", url)
            text = data.get("_text") or ""
            # 缓存键沿用 `efetch:abs:`（存的一直是整份 XML，不是解析结果）：换键会让
            # 既有缓存整体失效、白打一轮请求，而多解析出几个字段不需要缓存版本化。
            return self._parse_abstracts(text), self._parse_corrections(text)
        except (NotFoundError, TransportError):
            return {}, {}
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
        解析失败返回空字典，不抛（摘要是可选字段，见 _fetch_details）。"""
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

    @staticmethod
    def _parse_corrections(xml_text: str) -> Dict[str, Dict[str, Any]]:
        """efetch XML → `{uid: {"retraction_in": {...}|None, "eoc_in": {...}|None}}`。

        与 `_parse_abstracts` 同批解析同一份响应（见 `_fetch_details`）。每条声明给出
        `label`（RefSource 原文：期刊 + 卷期页 + DOI）、`doi`、`pmid`——信息量**超过现有
        两源**：OpenAlex 只有布尔 `is_retracted`，Crossref 有日期但不给声明所在刊期。

        **只认 `…In`，绝不认 `…Of`**：
          - `RetractionIn` = 本文**被**撤稿（要查的就是这个）；
          - `RetractionOf` = 本文**是**那份撤稿声明（极罕见，读反则撤稿态永不触发）。
        `ExpressionOfConcernIn`（本文被出具关注声明）同理，且它是**撤稿的中间态、不是撤稿**
        ——归属见 `_metadata`，不进 `retraction`。

        解析失败返回空字典、不抛（与摘要同一立场，见 `_fetch_details`）。
        """
        if not xml_text.strip():
            return {}
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError:
            return {}
        out: Dict[str, Dict[str, Any]] = {}
        for art in root.iter("PubmedArticle"):
            cit = art.find("MedlineCitation")
            if cit is None:
                continue
            pmid_el = cit.find("PMID")
            if pmid_el is None or not (pmid_el.text or "").strip():
                continue
            found: Dict[str, Any] = {}
            for node in cit.iter("CommentsCorrections"):
                ref_type = (node.get("RefType") or "").strip()
                if ref_type == _REFTYPE_RETRACTION_IN:
                    key = "retraction_in"
                elif ref_type == _REFTYPE_EOC_IN:
                    key = "eoc_in"
                else:
                    continue            # RetractionOf / CommentOn / ErratumIn … 都不是本文被撤稿
                if key in found:
                    continue            # 同型多条时留第一条，不拼接（多份声明极罕见）
                found[key] = PubMedClient._notice(node)
            if found:
                out[pmid_el.text.strip()] = found
        return out

    @staticmethod
    def _notice(node: ET.Element) -> Dict[str, Any]:
        """一条 CommentsCorrections → `{"label", "doi", "pmid"}`。

        `label` 是 RefSource 原文（期刊 + 卷期页 + DOI 的整句），原样留着供用户核对；
        DOI 另用正则单独取一份，方便直接点开那份声明。取不到就是 None——不从卷期页
        文本里凑一个 DOI 出来。
        """
        ref_el = node.find("RefSource")
        label = " ".join("".join(ref_el.itertext()).split()) if ref_el is not None else None
        pmid_el = node.find("PMID")
        pmid = (pmid_el.text or "").strip() if pmid_el is not None else None
        m = _REFSOURCE_DOI.search(label or "")
        doi = normalize_doi(m.group(1).rstrip(_DOI_TRAILING)) if m else None
        return {"label": label or None, "doi": doi, "pmid": pmid or None}

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
        abstracts, notices = self._fetch_details([uid])
        return self._hit(self._metadata(doc, abstracts.get(uid), notices.get(uid)), raw=doc,
                         retraction=self._retraction(doc, notices.get(uid)))

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
        abstracts, notices = self._fetch_details(uids)
        hits = []
        for uid in uids:
            doc = result.get(uid)
            if doc:
                hits.append(self._hit(self._metadata(doc, abstracts.get(uid), notices.get(uid)),
                                      raw=doc,
                                      retraction=self._retraction(doc, notices.get(uid))))
        return hits

    def search(self, query: str, filters: Optional[Dict[str, Any]] = None,
               limit: int = 20) -> List[SourceHit]:
        # 补充源：filters 空时与既有逐字节一致；非空时靠客户端侧兜底过滤（缓存原始 match 结果、
        # 过滤在读缓存之后，不串味）。year 用数字比较可靠，type 依赖 pubtype 归一。
        return self._postfilter(self.match(query, limit=limit), filters)

    @staticmethod
    def _metadata(doc: Dict[str, Any], abstract: Optional[str] = None,
                  notice: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        pubdate = doc.get("pubdate") or ""
        year = int(pubdate[:4]) if len(pubdate) >= 4 and pubdate[:4].isdigit() else None
        doi = None
        for aid in doc.get("articleids") or []:
            if aid.get("idtype") == "doi" and aid.get("value"):
                doi = normalize_doi(aid["value"])
                break
        types = doc.get("pubtype") or []
        # cited_by_count 有意不设键：E-utilities 不给被引数，设成 0 会把「未知」说成「零被引」。
        meta = {"title": doc.get("title"),
                "authors": [a.get("name") for a in (doc.get("authors") or []) if a.get("name")],
                "year": year, "venue": doc.get("fulljournalname"),
                "doi": doi, "type": types[0] if types else None,
                # `type` 仍取首项（既有行为不变），但**完整数组一并留下**：实测
                # 10.1056/NEJMoa2034577 的 pubtype 首项是 "Clinical Trial, Phase II"，
                # 只取首项就把 "Randomized Controlled Trial" 这个最有价值的证据类型标签
                # 丢了。医学场景按证据等级筛文献要靠这个数组。
                "pubtypes": list(types),
                "abstract": abstract,
                # 开放获取可得性（PMC 全文）。None = 该源未给出，≠ closed。
                "oa": PubMedClient._oa(doc)}
        eoc = (notice or {}).get("eoc_in")
        if eoc:
            # 关注声明（Expression of Concern）是**撤稿的中间态，不是撤稿**：期刊对该文
            # 存疑、尚未定论。故它单独成键陈列，**绝不进 `retraction`**——SourceHit.retraction
            # 一旦非空，paper-verify 就判 RETRACTED（judge.py 第 4 步），把「存疑」说成
            # 「已撤稿」是在替期刊下结论。呈现层作附加标记陈列即可，不新增第七态。
            # 只在真有声明时设键：缺键 = 没查到或没查过，绝不表述为「确认无关注声明」。
            meta["expression_of_concern"] = eoc
        return meta

    @staticmethod
    def _oa(doc: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """PMC 里的免费全文 → OA 记录（green / 仓储）。**零额外请求**——PMCID 就在
        `articleids` 里，`_metadata` 本来就在遍历那个数组找 DOI。

        **必须用 `idtype == "pmc"`，不要用 `"pmcid"`**：后者的值实测是
        `"pmc-id: PMC7745181;"`（带前缀与分号的脏格式），拼进 URL 就是个 404 链接。

        无 PMC → None（该源未给出），**不是 closed**：PubMed 压根不报 OA 状态，
        「不在 PMC」不等于「没有开放版本」（出版商自家 OA 与机构仓储都不进 PMC）。
        `version` 同样留 None——PMC 既存出版商终版也存作者稿，源不说是哪种就不猜。
        """
        for aid in doc.get("articleids") or []:
            if aid.get("idtype") == "pmc" and (aid.get("value") or "").strip():
                return oa_record(status="green", host="pmc", url_kind="landing",
                                 url=_PMC_ARTICLE_URL.format(aid["value"].strip()))
        return None

    @staticmethod
    def _retraction(doc: Dict[str, Any],
                    notice: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """撤稿标记，两路都是零额外请求：

        ① **快路径**——esummary 的 `pubtype` 数组含 `"Retracted Publication"`（题录已经
           在手，无需 efetch）；
        ② **详情**——efetch 同一份 XML 的 `CommentsCorrections[RefType=RetractionIn]`，
           给出撤稿声明的期刊卷期页、DOI 与 PMID。

        任一路成立即出标记：详情解析失败（efetch 挂了 / XML 不良构）时快路径仍在，
        为了拿不到详情把撤稿事实丢掉，是把次要字段的失败升级成主要事实的失败。

        `date_parts` 恒为 None：PubMed 不给结构化撤稿日期，RefSource 里那个日期是撤稿
        声明的**刊期文本**，硬解析成 date_parts 会把「声明发表于某日」说成「某日撤稿」。
        Crossref 命中时信息更全（带 Retraction Watch 的撤稿日期），judge.py 会优先取它。
        """
        flagged = any(str(t).strip().lower() == _RETRACTED_PUBTYPE
                      for t in (doc.get("pubtype") or []))
        ri = (notice or {}).get("retraction_in") or {}
        if not flagged and not ri:
            return None
        return {"type": "retraction",
                "label": ri.get("label") or "Retracted Publication",
                "date_parts": None, "source": "pubmed", "doi": ri.get("doi"),
                # 撤稿声明自己的 PMID（不是本文的）：用户可据此直接打开那份声明
                "notice_pmid": ri.get("pmid")}

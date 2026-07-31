"""Crossref 客户端：DOI 元数据 + 内置 Retraction Watch 撤稿数据（updated-by）。"""
from __future__ import annotations

import urllib.parse
from typing import Any, Dict, List, Optional

from ..models import SourceHit, normalize_doi
from ..transport import NotFoundError
from .base import (SourceClient, TYPE_MAP, author_details_or_empty, clean_jats_abstract,
                   normalize_orcid)


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
        authors = [CrossrefClient._author_name(a) for a in (msg.get("author") or [])]
        year = None
        parts = ((msg.get("issued") or {}).get("date-parts") or [[]])
        if parts and parts[0]:
            year = parts[0][0]
        containers = msg.get("container-title") or []
        # 摘要是 JATS XML 片段，须清洗成纯文本（clean_jats_abstract；剥不干净则返回 None，
        # 不把半截标签喂进笔记表）。投递率取决于出版商，给不出的条目仍由 dedup 从其他源补。
        # 与 S2 不同，这里**不必动缓存键**：crossref 的 URL 没有 select 参数，返回的是全字段，
        # abstract 本就躺在旧缓存的响应里（实测确认）。
        return {"title": titles[0] if titles else None, "authors": authors, "year": year,
                "venue": containers[0] if containers else None,
                "doi": normalize_doi(msg.get("DOI", "")) or None, "type": msg.get("type"),
                # 源没给就是 None，不补 0（「零被引」≠「该源不给这个数」）
                "cited_by_count": msg.get("is-referenced-by-count"),
                "abstract": clean_jats_abstract(msg.get("abstract")),
                "author_details": CrossrefClient._author_details(msg)}

    @staticmethod
    def _author_name(a: Dict[str, Any]) -> str:
        """given + family。`authors` 与 `author_details` 共用，免得两份拼接逻辑漂移。"""
        return " ".join(x for x in (a.get("given"), a.get("family")) if x)

    @staticmethod
    def _author_details(msg: Dict[str, Any]) -> List[Dict[str, Any]]:
        """作者的客观标识：ORCID + 机构。零额外请求（`raw` 存的就是完整 message）。

        Crossref 的 ORCID 覆盖实测很低（25 篇样本 46 个作者位里只有 2 个，4%），远不及
        OpenAlex 的 78%——但它独有 `authenticated-orcid`，是所有源里**唯一**能区分
        「作者本人登录验证过」与「出版商代填」的信号，拿得到就如实带上。

        无名的作者位跳过（机构作者只有 `name` 字段、没有 given/family）；`authors` 那侧
        维持原行为不过滤，免得在这次改动里夹带下游可见的行为变更。
        """
        out: List[Dict[str, Any]] = []
        for a in msg.get("author") or []:
            name = CrossrefClient._author_name(a)
            if not name:
                continue
            out.append({
                "name": name,
                "orcid": normalize_orcid(a.get("ORCID")),
                "affiliations": [f.get("name") for f in (a.get("affiliation") or [])
                                 if f.get("name")],
                # 源没给这个键 → None（未知），与 False（明确未验证）区分。
                "orcid_verified": a.get("authenticated-orcid"),
            })
        return author_details_or_empty(out)

    @staticmethod
    def _retraction(msg: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """本文是否**被**撤稿——读 updated-by，不是 update-to。

        两个字段方向相反，读错则 RETRACTED 态永不触发：
          update-to  = 本文更新了别人（本文自己是那份撤稿声明，极罕见）
          updated-by = 本文被别人更新（本文被撤稿，这才是要查的）
        实测 Wakefield 1998（10.1016/s0140-6736(97)11096-0）：update-to 为 None，
        updated-by 含 {type: retraction, source: retraction-watch, 2010-02-06}。
        """
        for upd in msg.get("updated-by") or []:
            label = f"{upd.get('type', '')} {upd.get('label', '')}".lower()
            if "retract" in label:
                return {"type": "retraction", "label": upd.get("label"),
                        "date_parts": (upd.get("updated") or {}).get("date-parts"),
                        "source": upd.get("source"), "doi": upd.get("DOI")}
        return None

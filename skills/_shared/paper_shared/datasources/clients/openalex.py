"""OpenAlex 客户端：跨注册机构的免费全学科元数据。"""
from __future__ import annotations

import urllib.parse
from typing import Any, Dict, List, Optional

from ..models import SourceHit, normalize_doi
from ..transport import NotFoundError
from .base import SourceClient, TYPE_MAP, restore_inverted_abstract


# `filter=openalex_id:A|B|C` 的 OR 上限（OpenAlex 对 filter 里的管道分隔取值限 50 个）
_OR_BATCH = 50
# `per-page` 的服务端上限
_PER_PAGE_MAX = 200


class OpenAlexClient(SourceClient):
    id = "openalex"

    def _fetch_work(self, doi: str) -> Optional[Dict[str, Any]]:
        """取单篇的**完整**响应（不经 _trim）。滚雪球要读 `referenced_works` 与 `id`，
        而 _trim 的白名单里没有 referenced_works——它只裁 raw，缓存里存的是完整响应，
        所以这里与 lookup_doi 共用同一个缓存键，不会多打一次请求。"""
        d = normalize_doi(doi)
        url = f"{self.config.base_url}/works/doi:{urllib.parse.quote(d, safe='/.')}"
        try:
            return self._cached_json(f"doi:{d}", url)
        except NotFoundError:
            return None

    @staticmethod
    def _short_id(oa_id: Optional[str]) -> Optional[str]:
        """`https://openalex.org/W2741809807` → `W2741809807`（filter 里只认短 ID）。"""
        if not oa_id:
            return None
        return str(oa_id).rstrip("/").rsplit("/", 1)[-1] or None

    def lookup_doi(self, doi: str) -> Optional[SourceHit]:
        data = self._fetch_work(doi)
        if data is None:
            return None
        return self._hit(self._metadata(data), raw=self._trim(data),
                         retraction=self._retraction(data))

    # ---- 滚雪球（capabilities: references / cited_by）----

    def _works_page(self, cache_key: str, url: str) -> List[SourceHit]:
        try:
            data = self._cached_json(cache_key, url)
        except NotFoundError:
            return []
        return [self._hit(self._metadata(w), raw=self._trim(w),
                          retraction=self._retraction(w))
                for w in data.get("results") or []]

    def references(self, doi: str, limit: int = 50) -> List[SourceHit]:
        """后向：`referenced_works` 只给 OpenAlex ID 列表，题录要再批量取一次
        （`filter=openalex_id:W1|W2|...`，每批 ≤50）。这是与 S2 的结构性差异：
        S2 一次调用直接回题录，OpenAlex 是两跳。"""
        work = self._fetch_work(doi)
        if not work:
            return []
        ids = [i for i in (self._short_id(x) for x in (work.get("referenced_works") or [])) if i]
        ids = ids[:max(1, int(limit))]
        out: List[SourceHit] = []
        for start in range(0, len(ids), _OR_BATCH):
            chunk = ids[start:start + _OR_BATCH]
            filt = urllib.parse.quote("|".join(chunk), safe="|")
            url = (f"{self.config.base_url}/works?filter=openalex_id:{filt}"
                   f"&per-page={len(chunk)}")
            out.extend(self._works_page(f"refs:{','.join(chunk)}", url))
        return out

    def cited_by(self, doi: str, limit: int = 50) -> List[SourceHit]:
        """前向：一次 `filter=cites:W...` 即可，但要先拿到本文的 OpenAlex ID。"""
        work = self._fetch_work(doi)
        if not work:
            return []
        wid = self._short_id(work.get("id"))
        if not wid:
            return []
        per = max(1, min(int(limit), _PER_PAGE_MAX))
        url = f"{self.config.base_url}/works?filter=cites:{wid}&per-page={per}"
        return self._works_page(f"cited_by:{wid}:{per}", url)

    def match(self, title: str, authors: Optional[List[str]] = None,
              year: Optional[int] = None, limit: int = 5) -> List[SourceHit]:
        q = urllib.parse.quote(title)
        url = f"{self.config.base_url}/works?filter=title.search:{q}&per-page={limit}"
        try:
            data = self._cached_json(f"match:{title.lower()}:{limit}", url)
        except NotFoundError:
            return []
        return [self._hit(self._metadata(w), raw=self._trim(w),
                          retraction=self._retraction(w))
                for w in data.get("results") or []]

    def search(self, query: str, filters: Optional[Dict[str, Any]] = None,
               limit: int = 20) -> List[SourceHit]:
        q = urllib.parse.quote(query)
        url = f"{self.config.base_url}/works?search={q}&per-page={limit}{self._filter_param(filters)}"
        try:
            data = self._cached_json(self._search_cache_key(query, limit, filters), url)
        except NotFoundError:
            return []
        hits = [self._hit(self._metadata(w), raw=self._trim(w),
                          retraction=self._retraction(w))
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
                "type": w.get("type"),
                # 被引数：源没给就是 None，**不补 0**——「零被引」与「该源不给这个数」
                # 是两件事，抹平了会让笔记表把未知说成已知。
                "cited_by_count": w.get("cited_by_count"),
                "abstract": restore_inverted_abstract(w.get("abstract_inverted_index"))}

    @staticmethod
    def _retraction(w: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """OpenAlex is_retracted——给撤稿检测加一路冗余，不单点依赖 Crossref。

        只有布尔标记，没有撤稿日期与撤稿声明 DOI，故 date_parts/doi 留空；
        Crossref updated-by 命中时信息更全（带 Retraction Watch 日期与声明 DOI）。
        """
        if not w.get("is_retracted"):
            return None
        return {"type": "retraction", "label": "Retraction",
                "date_parts": None, "source": "openalex", "doi": None}

    @staticmethod
    def _trim(w: Dict[str, Any]) -> Dict[str, Any]:
        # abstract_inverted_index 有意不进 raw：它是全文体积的倒排表，而还原后的纯文本
        # 已经在 metadata.abstract 里，留两份只是把缓存撑大。
        keep = ("id", "doi", "display_name", "publication_year", "type",
                "authorships", "primary_location", "is_retracted", "cited_by_count")
        return {k: w[k] for k in keep if k in w}

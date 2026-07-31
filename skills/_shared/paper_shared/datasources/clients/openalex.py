"""OpenAlex 客户端：跨注册机构的免费全学科元数据。"""
from __future__ import annotations

import urllib.parse
from typing import Any, Dict, List, Optional, Tuple

from ..models import AuthorCandidate, SourceHit, normalize_doi
from ..transport import NotFoundError
from .base import (SourceClient, TYPE_MAP, author_details_or_empty, normalize_orcid,
                   restore_inverted_abstract)


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

    # ---- 作者检索（capability: search_author）----

    def find_authors(self, name: str, limit: int = 10) -> Tuple[List[AuthorCandidate], int]:
        """按姓名查作者实体，返回（候选列表，源报告的总数）。

        **不做任何归并**——源给几个实体就是几条，按 ORCID 合并是检索策略层的事
        （search.py·merge_author_candidates），数据源层只负责取证。

        `display_name.search` 是**模糊匹配**：实测搜「周生华」会返回「周华生」。这里如实
        标 exact_name_match，不替调用方过滤掉——字序颠倒的也可能正是用户要找的人
        （英文库里中文名的姓名顺序本就混乱），滤掉就是替用户做判断。
        """
        q = urllib.parse.quote(name)
        per = max(1, min(int(limit), _PER_PAGE_MAX))
        url = f"{self.config.base_url}/authors?filter=display_name.search:{q}&per-page={per}"
        try:
            data = self._cached_json(f"authors:{name.lower()}:{per}", url)
        except NotFoundError:
            return [], 0
        total = ((data.get("meta") or {}).get("count")) or 0
        return ([self._author_candidate(a, name) for a in (data.get("results") or [])],
                int(total))

    def works_by_author(self, orcid: Optional[str] = None,
                        entity_id: Optional[str] = None,
                        filters: Optional[Dict[str, Any]] = None,
                        limit: int = 25) -> List[SourceHit]:
        """取某位作者的论文。二选一，**ORCID 优先**。

        用 ORCID 过滤能穿透源自己的实体拆分：实测 `0000-0003-3871-9099` 被拆成
        A5100765488（99 篇）与 A5041699772（6 篇），而 `filter=author.orcid:` 一次返回
        105 篇 = 99 + 6。所以有 ORCID 时绝不该按实体 ID 查——那样会漏掉一整块。
        """
        if orcid:
            key, filt = f"orcid:{orcid}", f"author.orcid:{urllib.parse.quote(orcid)}"
        elif entity_id:
            key, filt = f"aid:{entity_id}", f"author.id:{urllib.parse.quote(entity_id)}"
        else:
            raise ValueError("works_by_author 需要 orcid 或 entity_id 之一")
        per = max(1, min(int(limit), _PER_PAGE_MAX))
        extra = self._filter_param(filters)
        # _filter_param 自带 `&filter=` 前缀，这里要并进同一个 filter 段（逗号 = AND）
        if extra:
            filt = f"{filt},{extra.split('&filter=', 1)[1]}"
        url = f"{self.config.base_url}/works?filter={filt}&per-page={per}"
        try:
            data = self._cached_json(f"works_by:{key}:{per}:{extra}", url)
        except NotFoundError:
            return []
        hits = [self._hit(self._metadata(w), raw=self._trim(w), retraction=self._retraction(w))
                for w in data.get("results") or []]
        return self._postfilter(hits, filters)

    @classmethod
    def _author_candidate(cls, a: Dict[str, Any], queried: str) -> AuthorCandidate:
        name = a.get("display_name") or ""
        return AuthorCandidate(
            source=cls.id, name=name,
            entity_ids=[i for i in (cls._short_id(a.get("id")),) if i],
            orcid=normalize_orcid(a.get("orcid")),
            works_count=a.get("works_count") or 0,
            # 历年机构（带年份），不用 last_known_institutions——理由见 AuthorCandidate 注释
            affiliations=[{"name": (x.get("institution") or {}).get("display_name"),
                           "years": list(x.get("years") or [])}
                          for x in (a.get("affiliations") or [])
                          if (x.get("institution") or {}).get("display_name")],
            topics=[t.get("display_name") for t in (a.get("topics") or [])
                    if t.get("display_name")],
            name_variants=list(a.get("display_name_alternatives") or []),
            exact_name_match=name.strip().lower() == (queried or "").strip().lower(),
        )

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
                "abstract": restore_inverted_abstract(w.get("abstract_inverted_index")),
                "author_details": OpenAlexClient._author_details(w)}

    @staticmethod
    def _author_details(w: Dict[str, Any]) -> List[Dict[str, Any]]:
        """作者的客观标识：ORCID + 机构。数据已在 `authorships` 里（`_trim` 的白名单本就
        保着它），所以这是零额外请求的纯提取。

        **只陈列源给了什么，不做任何跨作者归并**——「这两个名字是不是同一个人」是概率
        推断，不归本层（实测 OpenAlex 自己都会把同一个 ORCID 拆成两个作者实体）。

        每条自带 `name`，不靠下标与 `authors` 对齐：跨源合并后作者列表的顺序与人数都可能
        不同，按位置对应会张冠李戴。机构**全留不截断**，呈现层要几个自己取。
        """
        out: List[Dict[str, Any]] = []
        for a in w.get("authorships") or []:
            author = a.get("author") or {}
            name = author.get("display_name")
            if not name:
                continue
            out.append({
                "name": name,
                "orcid": normalize_orcid(author.get("orcid")),
                "affiliations": [i.get("display_name")
                                 for i in (a.get("institutions") or [])
                                 if i.get("display_name")],
                # OpenAlex 不透出「该 ORCID 是否经作者本人验证」→ None（未知），
                # 与 Crossref 的 authenticated-orcid 共用三态，不假装成 False。
                "orcid_verified": None,
            })
        return author_details_or_empty(out)

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

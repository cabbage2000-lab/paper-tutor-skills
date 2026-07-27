"""SourceClient 基类：统一接口 + 缓存包装 + 默认探测实现（spec·第 5 节组件 4/7）。"""
from __future__ import annotations

import datetime
from typing import Any, Callable, Dict, List, Optional

from ..cache import Cache
from ..models import ProbeResult, SourceHit
from ..registry import SourceConfig
from ..transport import NotFoundError, Throttle, Transport, TransportError


def _utc_now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# canonical 文献类型 → 各源方言查询值（filters.type 落地；未列的 (源,类型) 组合不加原生
# type 过滤，靠 _postfilter 兜底）。canonical 集见 paper-search spec §8.3。
TYPE_MAP: Dict[str, Dict[str, str]] = {
    "crossref": {"journal-article": "journal-article", "conference-paper": "proceedings-article",
                 "book": "book", "book-chapter": "book-chapter", "preprint": "posted-content",
                 "thesis": "dissertation", "report": "report"},
    "openalex": {"journal-article": "article", "conference-paper": "article", "review": "review",
                 "book": "book", "book-chapter": "book-chapter", "preprint": "preprint",
                 "thesis": "dissertation", "report": "report"},
    "semantic_scholar": {"journal-article": "JournalArticle", "conference-paper": "Conference",
                         "review": "Review", "book": "Book"},
    "pubmed": {"journal-article": "Journal Article", "review": "Review"},
}

# 各源返回的 type 字符串 → canonical（_postfilter 归一用；归一不了返回 None，不误杀）
_TO_CANONICAL: Dict[str, str] = {
    "journal-article": "journal-article", "article": "journal-article",
    "journalarticle": "journal-article", "journal article": "journal-article",
    "proceedings-article": "conference-paper", "conference": "conference-paper",
    "preprint": "preprint", "posted-content": "preprint",
    "book": "book", "book-chapter": "book-chapter", "review": "review",
    "dissertation": "thesis", "thesis": "thesis", "report": "report",
}


def canonical_type(t: Optional[str]) -> Optional[str]:
    """把源返回的 type 归一到 canonical；无法归一返回 None（_postfilter 据此不误杀）。"""
    if not t:
        return None
    return _TO_CANONICAL.get(str(t).strip().lower())


class SourceClient:
    id: str = ""

    def __init__(self, config: SourceConfig, transport: Transport, cache: Cache,
                 throttle: Throttle, fresh: bool = False,
                 api_key: Optional[str] = None,
                 now_iso: Optional[Callable[[], str]] = None):
        self.config = config
        self.transport = transport
        self.cache = cache
        self.throttle = throttle
        self.fresh = fresh
        self.api_key = api_key   # 仅需凭证的源（S2/PubMed）使用；其余为 None
        self._now_iso = now_iso or _utc_now_iso
        self._last_from_cache = False

    # ---- 子类按能力矩阵实现 ----

    def lookup_doi(self, doi: str) -> Optional[SourceHit]:
        raise NotImplementedError(f"{self.id} 不支持 lookup_doi")

    def match(self, title: str, authors: Optional[List[str]] = None,
              year: Optional[int] = None, limit: int = 5) -> List[SourceHit]:
        raise NotImplementedError(f"{self.id} 不支持 match_title")

    def search(self, query: str, filters: Optional[Dict[str, Any]] = None,
               limit: int = 20) -> List[SourceHit]:
        raise NotImplementedError(f"{self.id} 不支持 search")

    # ---- 通用设施 ----

    def _cached_json(self, key: str, url: str,
                     headers: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        """缓存包装：fresh=True 跳过读、仍然写（投稿前终检拿最新撤稿状态）。"""
        ttl = self.config.cache_ttl_days or 7
        if not self.fresh:
            cached = self.cache.get(self.id, key, ttl_days=ttl)
            if cached is not None:
                self._last_from_cache = True
                return cached
        self._last_from_cache = False
        data = self.transport.get_json(url, headers=headers, throttle=self.throttle)
        self.cache.put(self.id, key, data)
        return data

    def _hit(self, metadata: Dict[str, Any], raw: Dict[str, Any],
             retraction: Optional[Dict[str, Any]] = None) -> SourceHit:
        return SourceHit(source=self.id, metadata=metadata, fetched_at=self._now_iso(),
                         retraction=retraction, raw=raw, from_cache=self._last_from_cache)

    # ---- filters 落地（search 用；paper-search spec §8.3）----

    @staticmethod
    def _search_cache_key(query: str, limit: int,
                          filters: Optional[Dict[str, Any]] = None) -> str:
        """检索缓存键。filters 为空时退回原字面 `search:{q}:{limit}`（保证既有回放测试不破）；
        非空时追加稳定指纹，避免带筛选 / 不带筛选两次检索在缓存里串味。"""
        base = f"search:{query.lower()}:{limit}"
        if not filters:
            return base
        yf, yt, typ = filters.get("year_from"), filters.get("year_to"), filters.get("type")
        return f"{base}:f={yf}-{yt}-{typ}"

    @staticmethod
    def _postfilter(hits: List[SourceHit],
                    filters: Optional[Dict[str, Any]] = None) -> List[SourceHit]:
        """客户端侧兜底过滤：解析后按 year / type 再过一遍。原生映射是提速，本函数是
        正确性安全网。year 用数字比较（对所有源可靠）；type 归一不了则保留（宁松勿误杀）。
        filters 空为 no-op。"""
        if not filters:
            return hits
        yf, yt, typ = filters.get("year_from"), filters.get("year_to"), filters.get("type")
        out: List[SourceHit] = []
        for h in hits:
            y = h.metadata.get("year")
            if yf is not None and (not isinstance(y, int) or y < yf):
                continue
            if yt is not None and (not isinstance(y, int) or y > yt):
                continue
            if typ is not None:
                ht = canonical_type(h.metadata.get("type"))
                if ht is not None and ht != typ:
                    continue
            out.append(h)
        return out

    def probe(self) -> ProbeResult:
        """默认探测：按注册表 probe 声明调对应能力，一次成功即 ok。"""
        spec = self.config.probe or {}
        kind, arg = spec.get("kind"), spec.get("arg")
        try:
            if kind == "lookup_doi":
                self.lookup_doi(arg)
            elif kind == "lookup_arxiv_id":
                if not hasattr(self, "lookup_arxiv_id"):
                    return ProbeResult(source=self.id, status="unavailable",
                                       role=self.config.role,
                                       reason=f"客户端 {self.id} 不支持 {kind} 探测")
                self.lookup_arxiv_id(arg)
            elif kind == "search":
                self.search(arg, limit=1)
            else:
                return ProbeResult(source=self.id, status="unavailable",
                                   role=self.config.role, reason="注册表未声明探测方式")
            return ProbeResult(source=self.id, status="ok", role=self.config.role)
        except TransportError as e:
            return ProbeResult(source=self.id, status="unavailable",
                               role=self.config.role, reason=f"{e.code}: {e.detail}")
        except NotFoundError:
            return ProbeResult(source=self.id, status="ok", role=self.config.role,
                               reason="探测样本未命中，但服务可达")
        except Exception as e:
            return ProbeResult(source=self.id, status="unavailable",
                               role=self.config.role,
                               reason=f"未预期异常: {type(e).__name__}: {e}")

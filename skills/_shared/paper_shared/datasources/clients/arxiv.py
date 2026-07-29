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
# submittedDate 区间必须两端都给（arXiv 不接受开区间），单边窗口用足够宽的哨兵补齐。
# 下界取 arXiv 上线前一年，上界取一个不会到达的年份。
_DATE_FLOOR = "19900101"
_DATE_CEIL = "20991231"


# 会破坏 arXiv 布尔表达式的字符：字段分隔符与分组 / 短语符号。整词剔除、不只去两端——
# `"code":x` 这种中间夹引号的 token，只 strip 两端会留下 `code"x`，照样把表达式带歪。
_BREAKING_CHARS = ':()"'


def _strip_breaking(s: str) -> str:
    for ch in _BREAKING_CHARS:
        s = s.replace(ch, "")
    return s.strip()


def _boolean_terms(query: str) -> str:
    """把词袋查询串组成 arXiv 能正确解析的布尔式 `(all:w1 AND all:w2 ...)`。

    只在带日期窗口时使用。为什么必须这样拼——2026-07-29 对真实 API 实测四种写法：

    | 写法 | 结果 |
    | --- | --- |
    | `all:<多个词> AND submittedDate:[...]` | 5 条**全部无关**（只有第一个词生效，实际返回窗口内全站新发） |
    | `all:"<整串>" AND submittedDate:[...]` | 0 条（精确短语太窄） |
    | `(all:w1 AND all:w2 ...) AND submittedDate:[...]` | 5 条全部相关 ✅ |
    | `(all:w1 OR all:w2 ...) AND submittedDate:[...]` | 5 条全部无关（OR 太松，命中任一常见词） |

    代价是逐词 AND 比无窗口路径的松散相关匹配**更严**（每个词都得出现）。日报场景下
    宁严勿滥：把窗口内全站新发当成用户主题的新发，比少召回几篇的危害大得多。
    """
    terms = [f"all:{t}" for t in (_strip_breaking(tok) for tok in query.split()) if t]
    if not terms:
        # 整串都是标点、切不出词：退回精确短语（大概率 0 命中）。绝不能只剩日期条件——
        # 那会把窗口内的全站新发当成用户主题的新发，正是上表第一行的错误结果。
        # 短语里也要剔除破坏字符，否则残留的引号 / 括号会让整个表达式失衡。
        return f'all:"{_strip_breaking(query)}"'
    return "(" + " AND ".join(terms) + ")"


def usable_terms(query: str) -> int:
    """能组进布尔式的词数。带日期窗口时调用方应先确认它 ≥ 1（见 paper-search CLI）。"""
    return sum(1 for tok in query.split() if _strip_breaking(tok))


def _is_iso_date(s: str) -> bool:
    """只认 `YYYY-MM-DD` 这一种形状，不做日历合法性校验（源头是 arXiv 自己的时间戳）。"""
    return (len(s) == 10 and s[4] == "-" and s[7] == "-"
            and s[:4].isdigit() and s[5:7].isdigit() and s[8:10].isdigit())


def _submitted_date_range(filters: Optional[Dict[str, Any]]) -> Optional[str]:
    """把 `date_from` / `date_to`（ISO `YYYY-MM-DD`）转成 arXiv 的 submittedDate 闭区间串。
    两个都没有返回 None（调用方据此走无日期窗口的历史路径）。"""
    if not filters:
        return None
    df, dt = filters.get("date_from"), filters.get("date_to")
    if not df and not dt:
        return None
    lo = df.replace("-", "") if df else _DATE_FLOOR
    hi = dt.replace("-", "") if dt else _DATE_CEIL
    return f"[{lo}0000 TO {hi}2359]"


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
        url = f"{self.config.base_url}/query?{self._search_params(query, filters, limit)}"
        try:
            # 改用共享缓存键（此前是自己拼的字面串，完全不含 filters）——日期窗口会改 URL，
            # 键不跟着变就会拿带窗口的缓存去顶不带窗口的检索。filters 为空时该函数返回的
            # 就是原字面 `search:{q}:{limit}`，历史缓存与回放测试照旧命中。
            # 年 / 类型不进 arxiv 的 URL（走客户端侧兜底），它们进键只是多存一份同内容缓存，
            # 无正确性影响，故不为 arxiv 单独裁剪一套键。
            text = self._cached_text(self._search_cache_key(query, limit, filters), url)
        except NotFoundError:
            return []
        hits = [self._hit_from_entry(e) for e in self._parse_entries(text)]
        # arxiv 无原生 year/type 过滤，靠客户端侧兜底；日期窗口已在上面原生下推，兜底再过一遍
        return self._postfilter(hits, filters)

    @staticmethod
    def _search_params(query: str, filters: Optional[Dict[str, Any]], limit: int) -> str:
        """组 query 串。无日期窗口时与历史写法逐字节一致（`search_query=all:<quote(q)>`），
        保证既有缓存与回放测试不破；有日期窗口时下推 arXiv 原生能力：

        - `submittedDate:[YYYYMMDD0000 TO YYYYMMDD2359]` —— 按提交时间的闭区间；
        - `sortBy=submittedDate&sortOrder=descending` —— 按提交时间倒序；
        - 查询词改成 `(all:w1 AND all:w2 ...)` 布尔式（见 `_boolean_terms` 的实测对照表，
          裸多词与 `AND` 同时出现时只有第一个词生效）。

        三者**只在设了日期窗口时才加**。默认排序（相关度）对主题检索更合适，日报要的是
        「最新」，两种需求不能共用一个默认值：按相关度取回的前 N 篇不是最新的 N 篇，
        `--per-source` 调多大都换不来时效性。
        """
        base = f"search_query=all:{urllib.parse.quote(query)}&max_results={limit}"
        window = _submitted_date_range(filters)
        if window is None:
            return base
        raw = f"{_boolean_terms(query)} AND submittedDate:{window}"
        return (f"search_query={urllib.parse.quote(raw)}&max_results={limit}"
                f"&sortBy=submittedDate&sortOrder=descending")

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
        # published 是完整 ISO 时间戳（如 2026-07-28T17:36:22Z），截出日级 YYYY-MM-DD。
        # 只有形如 YYYY-MM-DD 的前 10 位才认，避免把残缺值当日期用。
        date = published[:10] if _is_iso_date(published[:10]) else None

        cat_el = entry.find(f"{{{_ARXIV_NS}}}primary_category")
        category = cat_el.get("term") if cat_el is not None else None

        return {"id": short, "full_id": arxiv_id_full, "title": _text("title"),
                "authors": authors, "published": published, "year": year, "date": date,
                "doi": normalize_doi(doi) if doi else None,
                "category": category}

    @staticmethod
    def _metadata(raw: Dict[str, Any]) -> Dict[str, Any]:
        # date 是日级日期（YYYY-MM-DD）：paper-daily 的「今日 / 最近 N 天」时间窗靠它判定。
        # 此前 published 只用来算 year、归一化时被丢掉，宿主拿不到日级粒度。
        return {"title": raw.get("title"), "authors": raw.get("authors") or [],
                "year": raw.get("year"), "date": raw.get("date"), "venue": None,
                "doi": raw.get("doi"), "type": "preprint"}

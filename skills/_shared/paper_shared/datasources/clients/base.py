"""SourceClient 基类：统一接口 + 缓存包装 + 默认探测实现（spec·第 5 节组件 4/7）。"""
from __future__ import annotations

import datetime
import html
import re
import xml.etree.ElementTree as ET
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
#
# CSL-JSON 方言（`article-journal` / `paper-conference` / `chapter`）由 doi_meta 引入：
# 内容协商回的是 CSL 规范类型，与 Crossref 的 `journal-article` 恰好**词序相反**。缺了
# 这几行，中文 DOI 条目的 type 会归一成 None——filters.type 的客户端兜底过滤据此「宁松
# 勿误杀」放行，看着没坏，但 paper-search 加 `--type journal-article` 时中文条目就成了
# 唯一不被类型筛选约束的一档，用户读到的命中集与声明的筛选条件不符。
_TO_CANONICAL: Dict[str, str] = {
    "journal-article": "journal-article", "article": "journal-article",
    "journalarticle": "journal-article", "journal article": "journal-article",
    "article-journal": "journal-article",
    "proceedings-article": "conference-paper", "conference": "conference-paper",
    "paper-conference": "conference-paper",
    "preprint": "preprint", "posted-content": "preprint",
    "book": "book", "book-chapter": "book-chapter", "chapter": "book-chapter",
    "review": "review",
    "dissertation": "thesis", "thesis": "thesis", "report": "report",
}


def canonical_type(t: Optional[str]) -> Optional[str]:
    """把源返回的 type 归一到 canonical；无法归一返回 None（_postfilter 据此不误杀）。"""
    if not t:
        return None
    return _TO_CANONICAL.get(str(t).strip().lower())


def restore_inverted_abstract(index: Optional[Dict[str, Any]]) -> Optional[str]:
    """OpenAlex 的 `abstract_inverted_index` → 纯文本摘要。

    索引形如 `{"the": [0, 5], "cat": [1]}`——键是词、值是该词出现的位置列表。按位置铺回原序。

    两处刻意的保守：位置不连续（源数据缺词）时**跳过、不填占位符**，宁可句子短一截也不
    编内容；位置重复时后来者覆盖（同一位置只能有一个词，源数据自相矛盾时取其一，不拼接）。
    空索引与全非法位置一律返回 None，让调用方与「该源没给摘要」同等对待。
    """
    if not index or not isinstance(index, dict):
        return None
    slots: Dict[int, str] = {}
    for word, positions in index.items():
        for p in positions or []:
            # 只认非负整数位置。bool 是 int 的子类，显式排掉，免得 True 被当成位置 1。
            if isinstance(p, int) and not isinstance(p, bool) and p >= 0:
                slots[p] = word
    if not slots:
        return None
    return " ".join(slots[i] for i in sorted(slots))


# ---- JATS 摘要清洗（Crossref 的 abstract 是 XML 片段，不是纯文本）----

# 标签前缀：实测同一个字段里出现过 `jats:p`、无前缀的 `p`、以及 `ns3:p` 三种写法，
# 且**没有一处声明 xmlns** —— 直接喂 ET.fromstring 必报 "unbound prefix"。
# 因此统一把前缀剥掉，而不是去声明某个特定命名空间（前缀名是出版商任意取的）。
_JATS_PREFIX = re.compile(r"<(/?)[A-Za-z][\w.-]*:")
# 非 XML 标准实体（&nbsp; &mdash; …）会让解析直接失败，先转成字符；
# XML 的五个标准实体必须留着，否则 &lt; 变成真 `<` 会把结构冲烂。
_NON_XML_ENTITY = re.compile(r"&(?!(?:amp|lt|gt|quot|apos|#\d+|#x[0-9a-fA-F]+);)[a-zA-Z][a-zA-Z0-9]*;")
# 标签形态的判据。要求**闭合的 `>` 且首字符是字母**，所以摘要里合法的数学比较
# （`x < 5`、`a<b`、`p<0.05`）不会被当成标签。
#
# 有意**不用**贪婪的 `<[^>]*>`：在不良构数据上它会从数学比较符的 `<` 一路吃到下一个 `>`，
# 把中间的正文静默吞掉——实测 `p < 0.05 with unclosed <jats:bold>` 会丢掉
# "0.05 with unclosed"。静默残缺比留一个孤立的 `<` 有害得多：用户会把残缺摘要当完整的读。
_RESIDUAL_TAG = re.compile(r"<\s*/?\s*[A-Za-z][\w:.-]*(?:\s[^<>]*)?/?>")
_MAX_STRIP_ROUNDS = 3       # 病态输入的保险；出版商双重转义实测最多两层
_ENTITY = re.compile(r"&(?:#\d+|#x[0-9a-fA-F]+|\w+);")
# 「Abstract」这类词是标签、不是摘要内容，去掉；小节标题（Background / Methods…）要留。
_ABSTRACT_LABELS = {"abstract", "graphical abstract", "summary", "摘要", "abstract:"}
_LEADING_LABEL = re.compile(r"^(abstract|graphical abstract|summary|摘要)\s*[:：.]?\s+", re.I)


def _flat_text(node: ET.Element) -> str:
    """节点内全部文本折成单行。用 itertext() 而非 .text：正文里嵌着 <bold>/<sup>/<italic>
    等行内标签，只取 .text 会在第一个子标签处截断，把摘要砍掉半句。"""
    return " ".join("".join(node.itertext()).split())


def _is_abstract_label(text: str) -> bool:
    return text.strip().rstrip(":：.").lower() in _ABSTRACT_LABELS


def _finalize_text(text: str) -> str:
    """收尾清洗：反转义残余实体 + 剥残余标签，两者**交替**做到稳定。

    必须交替、且不止一轮，因为出版商普遍双重转义，实测三种都真实存在：
      - `&amp;amp;` 经 XML 解析只解到 `&amp;`，用户会在笔记表里看到字面 `&amp;`
        （10.47310/jpms202514s0159）；
      - `&amp;lt;.001` 解到 `&lt;`，本该显示成 `P < .001`（10.2196/preprints.65269）；
      - `&lt;p&gt;` 反转义后变成字面 `<p>`，于是又要再剥一遍标签
        （10.5539/hes.v6n3p72）。
    只做一遍、或只做其中一件，这三条都会带着可见的转义残渣进笔记表。
    """
    for _ in range(_MAX_STRIP_ROUNDS):
        before = text
        if _ENTITY.search(text):
            text = html.unescape(text)
        text = _RESIDUAL_TAG.sub(" ", text)
        if text == before:
            break
    return " ".join(text.split())


def _meaningful(text: Optional[str]) -> Optional[str]:
    """没有任何字母 / 汉字的「摘要」等同没有摘要。

    实测有出版商投递 `<jats:p>.</jats:p>`——一个句点（10.18502/kss.v3i6.2443）。把它当摘要
    交给三格起草档，等于请 AI 对着一个句点编方法学；如实标「无摘要，未起草」才是对的。
    判据是「有没有词」这个客观事实，不是主观的长度阈值——`[^\\W\\d_]` 对汉字同样成立。
    """
    if not text or not re.search(r"[^\W\d_]", text):
        return None
    return text


def _strip_tags(raw: str) -> Optional[str]:
    """降级路径：XML 解析失败（数据本身不良构）时按正则剥标签。

    只剥形态完整的标签，剥不掉的孤立 `<` **保留**而不是整条丢弃：它进 markdown 与 HTML
    都不形成标签（无害），而它也可能就是正文的一部分。三种坏结果里排序是——静默丢内容
    最坏，整条丢弃次之，留个孤立尖括号最轻。
    """
    return _LEADING_LABEL.sub("", _finalize_text(raw)) or None


def clean_jats_abstract(raw: Optional[str]) -> Optional[str]:
    """Crossref 的 `abstract`（JATS XML 片段）→ 纯文本。给不出干净结果就返回 None。

    结构化摘要按 `<sec><title>Methods</title><p>…</p></sec>` 拼成 `Methods: …`
    （与 PubMed 的 efetch 处理同一口径，两边产出形状一致）。顶层的 `<title>Abstract</title>`
    丢掉——那是标签不是内容。
    """
    if not raw or not isinstance(raw, str) or not raw.strip():
        return None
    body = _NON_XML_ENTITY.sub(lambda m: html.unescape(m.group(0)), raw.strip())
    body = _JATS_PREFIX.sub(r"<\1", body)
    try:
        # 片段常有多个并列根元素（title + 若干 p），必须包一层才是良构 XML
        root = ET.fromstring(f"<root>{body}</root>")
    except ET.ParseError:
        return _meaningful(_strip_tags(raw))
    parts: List[str] = []

    def _add(raw_text: Optional[str]) -> None:
        collapsed = " ".join((raw_text or "").split())
        if collapsed:
            parts.append(collapsed)

    # root.text 与 child.tail 是**标签外的裸文本**，两者都必须收：
    #   - 有出版商直接投递纯文本（一个标签都没有），只遍历子元素会把整段摘要丢成 None；
    #   - 混合内容（`裸文本 <p>段</p> 又是裸文本`）同理会丢掉标签之间的句子。
    _add(root.text)
    for child in root:
        tag = child.tag.lower()
        if tag == "sec":
            title_el = child.find("title")
            label = ""
            if title_el is not None:
                label = _flat_text(title_el)
                child.remove(title_el)      # 摘掉标题，剩下的才是这节正文
            text = _flat_text(child)
            if text:
                parts.append(f"{label}: {text}"
                             if label and not _is_abstract_label(label) else text)
        elif tag == "title" and _is_abstract_label(_flat_text(child)):
            pass                            # 「Abstract」是标签不是内容，丢掉
        else:
            _add(_flat_text(child))
        _add(child.tail)
    # 解析成功不等于清洗完成：XML 只解一层实体、也只认真正的标签，出版商的双重转义
    # 会留下字面的 `<p>` 与 `&amp;`（见 _finalize_text 的三个实测案例）。
    out = _finalize_text(" ".join(parts).strip())
    if not out:
        # 片段里只有一个「Abstract」标题、没有正文：等同该条没给摘要
        return None
    return _meaningful(_LEADING_LABEL.sub("", out))


# ---- 作者标识（ORCID）----

# ORCID 的规范形态是 4 组 4 字符，末位校验位可能是 X：`0000-0002-1825-0097`。
# 各源都给完整 URI 且 scheme 不一致（OpenAlex 给 https://orcid.org/…，Crossref 给
# http://orcid.org/… 的历史形式），不剥成裸 ID 就跨源比不起来。
_ORCID_RE = re.compile(r"(\d{4}-\d{4}-\d{4}-\d{3}[\dX])\s*$", re.I)


def normalize_orcid(raw: Optional[str]) -> Optional[str]:
    """任意形态的 ORCID → 裸 ID（`0000-0002-1825-0097`）；认不出返回 None。

    **有意不做 ISO 7064 校验位验证**：这些 ID 来自源 API 而非用户输入，校验的唯一收益是
    挡住源的脏数据，而一旦本地实现有偏差就会静默丢弃真实标识。宁可透传一个源给错的 ID
    （用户点进去 404，一眼可辨），也不做会误杀的清洗——格式对不上才丢。
    """
    if not raw:
        return None
    m = _ORCID_RE.search(str(raw).strip())
    return m.group(1).upper() if m else None


def author_details_or_empty(details: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """全员既无 ORCID 又无机构时收敛成 `[]`，否则原样返回。

    不返回一串空壳：空壳会让下游把「源没给标识」显示成「这个人没有 ORCID」，两者差着
    一个事实。收敛成空列表后，呈现层与「该源不提供作者标识」同等对待。
    """
    return details if any(d.get("orcid") or d.get("affiliations") for d in details) else []


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

    def references(self, doi: str, limit: int = 50) -> List[SourceHit]:
        """后向滚雪球：本文引了谁。空列表 = 查到了但该文没有参考文献记录。"""
        raise NotImplementedError(f"{self.id} 不支持 references")

    def cited_by(self, doi: str, limit: int = 50) -> List[SourceHit]:
        """前向滚雪球：谁引了本文。空列表 = 查到了但尚无被引记录。"""
        raise NotImplementedError(f"{self.id} 不支持 cited_by")

    def find_authors(self, name: str, limit: int = 10):
        """按姓名查作者实体，返回（候选列表，源报告的总数）。"""
        raise NotImplementedError(f"{self.id} 不支持 search_author")

    def works_by_author(self, orcid: Optional[str] = None,
                        entity_id: Optional[str] = None,
                        filters: Optional[Dict[str, Any]] = None,
                        limit: int = 25) -> List[SourceHit]:
        """取某位作者的论文（ORCID 或源实体 ID 二选一）。"""
        raise NotImplementedError(f"{self.id} 不支持 search_author")

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
        非空时追加稳定指纹，避免带筛选 / 不带筛选两次检索在缓存里串味。

        日期窗口只在存在时才追加 `:d=...` 段——否则既有「年 / 类型」指纹的键会整体位移，
        已缓存的检索全部失效。"""
        base = f"search:{query.lower()}:{limit}"
        if not filters:
            return base
        yf, yt, typ = filters.get("year_from"), filters.get("year_to"), filters.get("type")
        key = f"{base}:f={yf}-{yt}-{typ}"
        df, dt = filters.get("date_from"), filters.get("date_to")
        if df or dt:
            key = f"{key}:d={df}-{dt}"
        return key

    @staticmethod
    def _postfilter(hits: List[SourceHit],
                    filters: Optional[Dict[str, Any]] = None) -> List[SourceHit]:
        """客户端侧兜底过滤：解析后按 year / date / type 再过一遍。原生映射是提速，本函数是
        正确性安全网。year 与 date 用可靠比较（数字 / ISO 字符串字典序）；type 归一不了则保留
        （宁松勿误杀）。filters 空为 no-op。

        日期缺失的条目在设了日期边界时**排除**（同 year 的处理，不同于 type）：日期窗口是
        「这一天有没有新发」的判断依据，把无日期的条目留在窗口内会让日报把窗口外的文献
        当成新发。目前只有 arXiv 提供日级日期，所以给不提供日期的源加日期窗口会 0 命中——
        门面如实记 `outcome=empty`（查过、0 命中），不是静默丢弃。"""
        if not filters:
            return hits
        yf, yt, typ = filters.get("year_from"), filters.get("year_to"), filters.get("type")
        df, dt = filters.get("date_from"), filters.get("date_to")
        out: List[SourceHit] = []
        for h in hits:
            y = h.metadata.get("year")
            if yf is not None and (not isinstance(y, int) or y < yf):
                continue
            if yt is not None and (not isinstance(y, int) or y > yt):
                continue
            if df or dt:
                d = h.metadata.get("date")
                if not isinstance(d, str) or len(d) < 10:
                    continue
                if df and d[:10] < df:
                    continue
                if dt and d[:10] > dt:
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

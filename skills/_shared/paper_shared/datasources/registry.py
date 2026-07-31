"""数据源注册表：声明式维护各源的端点、限流、能力矩阵与覆盖声明。

数据源清单是产品输出的一部分（核验报告「已查源清单」、search 覆盖方式声明
均由本注册表生成），不是散落在实现里的常量。spec·第 7 节。
"""
from __future__ import annotations

import json
import pathlib
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

_DEFAULT_PATH = pathlib.Path(__file__).with_name("registry.json")
_VALID_KINDS = {"api", "guided"}
_VALID_ROLES = {"core", "supplementary"}
_VALID_CAPS = {"lookup_doi", "lookup_arxiv_id", "match_title", "search", "retraction", "route",
               # import_export：该源的**官方导出引文文件**可被解析入表（guided 源专用能力，
               # 不是自动检索）。中文库无免费 API 且站内接口有 robots.txt 明示禁止，故走
               # 「用户站内检索 → 官方导出 → paper-search/scripts/parse_export.py 解析」。
               "import_export",
               # 作者检索（paper-search 的 --find-author / --author-works）：按姓名取源的
               # 作者实体候选，以及取某位作者的论文。目前只有 OpenAlex 提供免费的作者
               # 实体端点（S2 有但要 key 且限流严），所以这一路是**单源**，覆盖声明要如实说。
               "search_author",
               # 滚雪球两向（paper-search 的 --snowball）：
               #   references = 后向，取本文引了谁（补经典文献——年份降序恰恰把经典排到最末）
               #   cited_by   = 前向，取谁引了本文（补最新跟进）
               # 只给真能一次调用回题录的源；Crossref 的 reference 数组投递率不稳、且无前向，不给。
               "references", "cited_by"}


class RegistryError(Exception):
    """注册表 schema 校验失败。"""


@dataclass
class SourceConfig:
    id: str
    name_zh: str
    kind: str                      # api | guided
    role: str                      # core | supplementary
    base_url: Optional[str] = None
    capabilities: List[str] = field(default_factory=list)
    rate_limit: Optional[Dict[str, Any]] = None
    auth: Optional[Dict[str, Any]] = None
    cache_ttl_days: Optional[float] = None
    probe: Optional[Dict[str, Any]] = None
    coverage_zh: str = ""
    docs_url: str = ""


class Registry:
    def __init__(self, sources: List[SourceConfig]):
        self._by_id = {s.id: s for s in sources}
        self._order = [s.id for s in sources]

    @classmethod
    def load(cls, path: Optional[pathlib.Path] = None) -> "Registry":
        p = pathlib.Path(path) if path else _DEFAULT_PATH
        with open(p, encoding="utf-8") as f:
            return cls.from_data(json.load(f))

    @classmethod
    def from_data(cls, data: Dict[str, Any]) -> "Registry":
        sources = []
        for raw in data.get("sources", []):
            for required in ("id", "name_zh", "kind", "role"):
                if required not in raw:
                    raise RegistryError(f"源条目缺少必填字段 {required}: {raw!r}")
            if raw["kind"] not in _VALID_KINDS:
                raise RegistryError(f"未知 kind: {raw['kind']}")
            if raw["role"] not in _VALID_ROLES:
                raise RegistryError(f"未知 role: {raw['role']}")
            caps = raw.get("capabilities") or []
            unknown = set(caps) - _VALID_CAPS
            if unknown:
                raise RegistryError(f"未知能力: {unknown}")
            if raw["kind"] == "api" and not raw.get("base_url"):
                raise RegistryError(f"api 源必须有 base_url: {raw['id']}")
            sources.append(SourceConfig(
                id=raw["id"], name_zh=raw["name_zh"], kind=raw["kind"], role=raw["role"],
                base_url=raw.get("base_url"), capabilities=list(caps),
                rate_limit=raw.get("rate_limit"), auth=raw.get("auth"),
                cache_ttl_days=raw.get("cache_ttl_days"), probe=raw.get("probe"),
                coverage_zh=raw.get("coverage_zh", ""), docs_url=raw.get("docs_url", "")))
        return cls(sources)

    def all(self) -> List[SourceConfig]:
        return [self._by_id[i] for i in self._order]

    def get(self, source_id: str) -> SourceConfig:
        return self._by_id[source_id]

    def api_sources(self) -> List[SourceConfig]:
        return [s for s in self.all() if s.kind == "api"]

    def guided_sources(self) -> List[SourceConfig]:
        return [s for s in self.all() if s.kind == "guided"]

    def with_capability(self, cap: str) -> List[SourceConfig]:
        return [s for s in self.all() if cap in s.capabilities]

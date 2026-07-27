"""健康探测组装：每源一个已知良性请求，三态输出（spec·第 5 节组件 7）。

整体判定：核心源全 ok→ok；核心源有 partial 或部分 unavailable→degraded；
核心源全 unavailable→offline；补充源（pubmed/eric）不拉低整体。
"""
from __future__ import annotations

from typing import Dict, List, Optional

from .cache import Cache
from .clients import build_clients
from .models import ProbeResult
from .registry import Registry
from .transport import Transport

# 可探测的核心数据源。注意：不能简单等同于 registry role=="core"——doi_ra 虽为
# core 但只有 route 能力、无标准客户端，会以 unavailable 混入 probe 结果污染整体判定。
# TODO(高度)：让 run() 在源级区分「可探测源」与 role，从根上消除这份 id 常量
# （见评审 Altitude #1）；届时 overall 可直接按 ProbeResult.role 判定。
CORE_IDS = {"crossref", "openalex", "semantic_scholar", "arxiv"}


class ProbeEngine:
    def __init__(self, registry: Registry, transport: Optional[Transport] = None,
                 cache: Optional[Cache] = None, include_supplementary: bool = True):
        self.registry = registry
        self.transport = transport or Transport(user_agent="Paper-datasources/0")
        self.cache = cache or Cache()
        self.include_supplementary = include_supplementary

    def run(self) -> List[ProbeResult]:
        clients = self._make_clients()
        results: List[ProbeResult] = []
        for src in self.registry.api_sources():
            if src.role == "supplementary" and not self.include_supplementary:
                continue
            if src.id not in clients:
                results.append(ProbeResult(source=src.id, status="unavailable",
                                           role=src.role, reason="无客户端实现"))
                continue
            results.append(clients[src.id].probe())
        return results

    def _make_clients(self) -> Dict:
        return build_clients(self.registry, self.transport, self.cache)

    @staticmethod
    def overall(results: List[ProbeResult]) -> str:
        core = [r for r in results if r.source in CORE_IDS]
        if not core:
            return "offline"
        core_ok = [r for r in core if r.status == "ok"]
        core_unavail = [r for r in core if r.status == "unavailable"]
        if len(core_unavail) == len(core):
            return "offline"
        if len(core_ok) == len(core):
            return "ok"
        return "degraded"

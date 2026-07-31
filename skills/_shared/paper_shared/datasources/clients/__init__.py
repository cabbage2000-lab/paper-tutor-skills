"""客户端注册与实例化工厂：source_id → 客户端类，batch/search/probe 共用 build_clients。"""
from __future__ import annotations

import os
from typing import Dict, Iterable, Optional, Type

from ..cache import Cache
from ..registry import Registry, SourceConfig
from ..transport import Throttle, Transport
from .base import SourceClient
from .crossref import CrossrefClient
from .openalex import OpenAlexClient
from .semantic_scholar import SemanticScholarClient
from .arxiv import ArxivClient
from .pubmed import PubMedClient
from .eric import EricClient
from .doi_meta import DoiMetaClient

CLIENT_CLASSES: Dict[str, Type[SourceClient]] = {
    CrossrefClient.id: CrossrefClient,
    OpenAlexClient.id: OpenAlexClient,
    SemanticScholarClient.id: SemanticScholarClient,
    ArxivClient.id: ArxivClient,
    PubMedClient.id: PubMedClient,
    EricClient.id: EricClient,
    DoiMetaClient.id: DoiMetaClient,
}


def _resolve_api_key(cfg: SourceConfig) -> Optional[str]:
    """读取源在注册表声明的凭证环境变量（无声明或未设置则 None）。"""
    if not cfg.auth or not cfg.auth.get("key_env"):
        return None
    return os.environ.get(cfg.auth["key_env"])


def build_clients(registry: Registry, transport: Transport, cache: Cache,
                  fresh: bool = False,
                  only: Optional[Iterable[str]] = None) -> Dict[str, SourceClient]:
    """按注册表实例化客户端。only 限定只建指定源（search 只需部分源，避免全量构造）。

    每源据限流档（有无凭证决定 tier）建独立 Throttle；凭证经 registry.auth 判别，
    env 只读一次同时用于档位判定与注入客户端。
    """
    wanted = set(only) if only is not None else None
    clients: Dict[str, SourceClient] = {}
    for src_id, cls in CLIENT_CLASSES.items():
        if wanted is not None and src_id not in wanted:
            continue
        cfg = registry.get(src_id)
        api_key = _resolve_api_key(cfg)
        tier = "with_credential" if api_key else "anonymous"
        interval = (cfg.rate_limit or {}).get(tier, {}).get("min_interval_s", 1.0)
        # Throttle 复用 transport 的 sleep：生产为真实 time.sleep（限流照常），
        # 测试注入 no-op transport 时限流 sleep 亦随之 no-op，探测/批处理测试不再真实等待。
        clients[src_id] = cls(cfg, transport, cache,
                              Throttle(interval, sleep=transport.sleep),
                              fresh=fresh, api_key=api_key)
    return clients

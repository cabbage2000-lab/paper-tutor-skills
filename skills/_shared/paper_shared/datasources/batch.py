"""批处理引擎：源间并发、源内串行节流、断点续验、剩余时间预估。

spec·第 5 节组件 6、第 8 节工程约束、第 9 节错误分类。
断点续验状态文件路径由调用方传入——库不硬编码 .paper/（「目录约定是增强
不是依赖」）。
"""
from __future__ import annotations

import hashlib
import json
import os
import pathlib
import queue
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple

from .cache import Cache
from .clients import build_clients
from .clients.base import SourceClient
from .models import (BatchResult, Evidence, Ref, SourceHit, SourceQuery)
from .registry import Registry
from .routing import CONSERVATIVE_SOURCES, RoutePlan, route
from .transport import NotFoundError, Transport, TransportError


def _fingerprint(refs: List[Ref]) -> str:
    h = hashlib.sha256()
    for r in sorted(refs, key=lambda x: x.id):
        h.update(r.id.encode("utf-8"))
        h.update((r.doi or "").encode("utf-8"))
        h.update((r.title or "").encode("utf-8"))
    return h.hexdigest()


@dataclass
class _SourceTask:
    ref: Ref
    plan: RoutePlan
    source: str


class BatchEngine:
    def __init__(self, registry: Registry, transport: Optional[Transport] = None,
                 cache: Optional[Cache] = None, fresh: bool = False,
                 num_workers: Optional[int] = None, state_path: Optional[pathlib.Path] = None,
                 progress: Optional[Callable[[str], None]] = None):
        self.registry = registry
        self.transport = transport or Transport(user_agent="Paper-datasources/0")
        self._transport = self.transport
        self.cache = cache or Cache()
        self.fresh = fresh
        self.num_workers = num_workers or 4
        self.state_path = pathlib.Path(state_path) if state_path else None
        self.progress = progress or (lambda s: None)
        self._fp: Optional[str] = None   # 断点续验指纹缓存（见 _fingerprint）

    def run(self, refs: List[Ref]) -> BatchResult:
        """真实运行路径：route() 判别 + 实例化客户端 + 并发查询。"""
        evidences, done = self._load_state(refs)
        plans: Dict[str, RoutePlan] = {}
        all_tasks: List[_SourceTask] = []
        for ref in refs:
            if ref.id in done:
                continue
            if ref.doi:
                plan = route(ref.doi, self.transport, self.cache)
            else:
                plan = RoutePlan(doi_ra=None, sources=list(CONSERVATIVE_SOURCES))
            plans[ref.id] = plan
            for src in plan.sources:
                all_tasks.append(_SourceTask(ref=ref, plan=plan, source=src))

        clients = self._make_clients()
        results, stats = self._dispatch(all_tasks, clients)
        return self._assemble(refs, plans, results, stats, evidences, done)

    # ---- 注入测试钩子（test_batch 走这条路径）----

    def _run_with_injected(self, refs: List[Ref]) -> BatchResult:
        """测试专用：route 结果与查询结果由 engine._route_by_ref / _fake_query 注入。"""
        evidences, done = self._load_state(refs)
        plans: Dict[str, RoutePlan] = getattr(self, "_route_by_ref", {})
        all_tasks: List[_SourceTask] = []
        for ref in refs:
            if ref.id in done:
                continue
            for src in plans.get(ref.id, RoutePlan(doi_ra=None, sources=[])).sources:
                all_tasks.append(_SourceTask(ref=ref, plan=plans.get(ref.id), source=src))
        fake_query = getattr(self, "_fake_query", lambda ref, plan: {})
        results: Dict[str, Dict[str, Tuple[Any, str, Optional[str]]]] = {}
        for ref in refs:
            if ref.id in done:
                continue
            results[ref.id] = fake_query(ref, plans.get(ref.id, RoutePlan(doi_ra=None)))
            done.add(ref.id)
            self._save_state(refs, evidences, done)
        stats = {"total_refs": len(refs), "cached_refs": len(evidences),
                 "sources_queried": len({t.source for t in all_tasks})}
        return self._assemble(refs, plans, results, stats, evidences, done)

    # ---- 内部组件 ----

    def _make_clients(self) -> Dict[str, SourceClient]:
        return build_clients(self.registry, self.transport, self.cache, fresh=self.fresh)

    def _dispatch(self, tasks: List[_SourceTask],
                  clients: Dict[str, SourceClient]
                  ) -> Tuple[Dict[str, Dict[str, Tuple[Any, str, Optional[str]]]],
                             Dict[str, Any]]:
        task_q: queue.Queue[Optional[_SourceTask]] = queue.Queue()
        for t in tasks:
            task_q.put(t)
        for _ in range(self.num_workers):
            task_q.put(None)

        results: Dict[str, Dict[str, Tuple[Any, str, Optional[str]]]] = {}
        lock = threading.Lock()
        total = len(tasks)
        completed = [0]
        start = time.monotonic()

        def worker():
            while True:
                t = task_q.get()
                if t is None:
                    task_q.task_done()
                    return
                outcome = self._query_one(clients[t.source], t)
                with lock:
                    results.setdefault(t.ref.id, {})[t.source] = outcome
                    completed[0] += 1
                    done_now = completed[0]
                    if total > 0 and done_now % 5 == 0:
                        elapsed = max(time.monotonic() - start, 0.001)
                        rate = done_now / elapsed
                        remaining = (total - done_now) / rate
                        self.progress(
                            f"[{done_now}/{total}] 剩约 {remaining:.0f}s")
                task_q.task_done()

        threads = [threading.Thread(target=worker) for _ in range(self.num_workers)]
        for th in threads:
            th.start()
        for th in threads:
            th.join()

        stats = {"total_tasks": total, "elapsed_s": round(time.monotonic() - start, 2)}
        return results, stats

    def _query_one(self, client: SourceClient,
                   t: _SourceTask) -> Tuple[Optional[SourceHit], str, Optional[str]]:
        cfg = self.registry.get(t.source)
        try:
            if "lookup_doi" in cfg.capabilities and t.ref.doi:
                hit = client.lookup_doi(t.ref.doi)
                outcome = "hit" if hit else "miss"
                return hit, outcome, None
            if t.ref.title:
                hits = client.match(t.ref.title, authors=t.ref.authors, year=t.ref.year)
                if hits:
                    return hits[0], "hit", None
                return None, "miss", None
            return None, "miss", None
        except TransportError as e:
            return None, "error", e.code
        except NotFoundError:
            return None, "miss", None

    def _assemble(self, refs: List[Ref], plans: Dict[str, RoutePlan],
                  results: Dict[str, Dict[str, Tuple[Any, str, Optional[str]]]],
                  stats: Dict[str, Any],
                  evidences: Dict[str, Evidence], done: set) -> BatchResult:
        all_errors: List[str] = []
        cache_hits = 0
        total_queries = 0
        source_call_counts: Dict[str, int] = {}
        for ref in refs:
            if ref.id in evidences:
                continue
            plan = plans.get(ref.id, RoutePlan(doi_ra=None))
            sq_list: List[SourceQuery] = []
            hit_list: List[SourceHit] = []
            for src, (hit, outcome, err) in (results.get(ref.id) or {}).items():
                was_cached = hit.from_cache if hit else False
                sq_list.append(SourceQuery(source=src, query_kind="doi" if ref.doi else "title_match",
                                           outcome=outcome, error=err,
                                           from_cache=was_cached))
                source_call_counts[src] = source_call_counts.get(src, 0) + 1
                total_queries += 1
                if was_cached:
                    cache_hits += 1
                if err:
                    all_errors.append(err)
                if hit:
                    hit_list.append(hit)
            ev = Evidence(ref_id=ref.id, input=ref, doi_ra=plan.doi_ra,
                          route_note=plan.route_note, queries=sq_list, hits=hit_list)
            evidences[ref.id] = ev
            done.add(ref.id)
            self._save_state(refs, evidences, done)

        network = "ok"
        if all_errors:
            error_set = set(all_errors)
            if error_set <= {"TIMEOUT", "CONN_FAILED", "DNS_FAIL"}:
                network = "offline" if len(all_errors) > 5 else "degraded"
            else:
                network = "degraded"
        stats["network_status"] = network
        stats["cache_hits"] = cache_hits
        stats["cache_hit_rate"] = round(cache_hits / total_queries, 3) if total_queries else 0.0
        stats["source_call_counts"] = source_call_counts
        return BatchResult(evidences=evidences, stats=stats, network_status=network)

    # ---- 状态文件（断点续验）----

    def _fingerprint(self, refs: List[Ref]) -> str:
        """指纹只依赖 refs（一次 run 内不变），首次算后缓存——避免每条 ref 落盘时
        重算全量 sha256（否则 N 条 ref → O(N²) 哈希）。"""
        if self._fp is None:
            self._fp = _fingerprint(refs)
        return self._fp

    def _load_state(self, refs: List[Ref]) -> Tuple[Dict[str, Evidence], set]:
        if self.state_path is None or not self.state_path.exists():
            return {}, set()
        with open(self.state_path, encoding="utf-8") as f:
            data = json.load(f)
        if data.get("fingerprint") != self._fingerprint(refs):
            raise RuntimeError(
                f"状态文件指纹不匹配：输入已变更，无法续跑（state={self.state_path}）")
        evidences = {k: Evidence.from_dict(v) for k, v in (data.get("evidences") or {}).items()}
        return evidences, set(data.get("done") or [])

    def _save_state(self, refs: List[Ref], evidences: Dict[str, Evidence], done: set) -> None:
        if self.state_path is None:
            return
        data = {"fingerprint": self._fingerprint(refs),
                "evidences": {k: v.to_dict() for k, v in evidences.items()},
                "done": sorted(done)}
        tmp = self.state_path.with_suffix(self.state_path.suffix + ".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, self.state_path)

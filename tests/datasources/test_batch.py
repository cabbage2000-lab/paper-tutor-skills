from __future__ import annotations

import json
import pathlib
import tempfile
import threading
import unittest

from paper_shared.datasources.batch import BatchEngine
from paper_shared.datasources.cache import Cache
from paper_shared.datasources.models import Ref
from paper_shared.datasources.registry import Registry
from paper_shared.datasources.routing import RoutePlan
from paper_shared.datasources.transport import Throttle, Transport
from tests.datasources.fakes import FakeOpener, FakeResponse


class FakeBatchEngine(BatchEngine):
    """绕过 route() 与真实客户端，用脚本化的 plan + hit 注入确定性。"""

    def __init__(self, registry, plans, hits_map, cache=None, state_path=None, progress=None):
        transport = Transport(user_agent="Paper-test/0", opener=FakeOpener([]),
                              sleep=lambda s: None)
        super().__init__(registry, transport=transport, cache=cache,
                         state_path=state_path, progress=progress)
        self._plans = plans          # ref_id -> RoutePlan
        self._hits_map = hits_map    # ref_id -> {source: SourceHit}

    def _route(self, doi, **kw):
        # 默认 plan：查找 _plans[ref_id]，但 _route 不知道 ref_id——用栈跟踪法
        # 这里简化为返回统一 plan
        return next(iter(self._plans.values()))

    def _make_clients(self):
        return {}  # 不实例化真实客户端；hit 注入走 _query_sources 重写


class TestBatchEngine(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.registry = Registry.load()

    def tearDown(self):
        self.tmp.cleanup()

    def _refs(self):
        return [Ref(id="r1", doi="10.1038/nature12373", title="Thermometry"),
                Ref(id="r2", doi="10.3969/j.issn.1000", title="中文论文"),
                Ref(id="r3", title="No DOI paper")]

    def test_run_collects_evidence_for_each_ref(self):
        engine = BatchEngine(self.registry,
                             transport=Transport(user_agent="t",
                                                 opener=FakeOpener([]),
                                                 sleep=lambda s: None),
                             cache=Cache(pathlib.Path(self.tmp.name) / "c.db"))
        # 用 mock 替换 route 和客户端查询
        plans = {
            "r1": RoutePlan(doi_ra="Crossref", sources=["crossref", "openalex"]),
            "r2": RoutePlan(doi_ra="ISTIC", sources=[], route_note="ISTIC..."),
            "r3": RoutePlan(doi_ra=None, sources=["crossref"]),
        }

        from paper_shared.datasources.models import SourceHit
        def fake_query(ref, plan):
            return {  # source -> (SourceHit|None, outcome, error)
                "r1": {"crossref": (SourceHit(source="crossref", metadata={"title": "T"},
                                              fetched_at="2026-07-22T00:00:00Z"), "hit", None),
                       "openalex": (None, "miss", None)},
                "r2": {},
                "r3": {"crossref": (None, "miss", None)},
            }.get(ref.id, {})

        engine._route_by_ref = plans
        engine._fake_query = fake_query

        result = engine._run_with_injected(self._refs())

        self.assertEqual(set(result.evidences.keys()), {"r1", "r2", "r3"})
        ev1 = result.evidences["r1"]
        self.assertEqual(ev1.doi_ra, "Crossref")
        self.assertEqual(len(ev1.hits), 1)
        self.assertEqual(ev1.queries[0].source, "crossref")
        self.assertEqual(ev1.queries[0].outcome, "hit")
        ev2 = result.evidences["r2"]
        self.assertEqual(ev2.doi_ra, "ISTIC")
        self.assertEqual(ev2.hits, [])
        self.assertIsNotNone(ev2.route_note)
        ev3 = result.evidences["r3"]
        self.assertIsNone(ev3.doi_ra)

    def test_state_file_resume(self):
        state = pathlib.Path(self.tmp.name) / "state.json"
        engine = BatchEngine(self.registry,
                             transport=Transport(user_agent="t",
                                                 opener=FakeOpener([]),
                                                 sleep=lambda s: None),
                             cache=Cache(pathlib.Path(self.tmp.name) / "c.db"),
                             state_path=state)
        from paper_shared.datasources.models import SourceHit
        engine._route_by_ref = {
            "r1": RoutePlan(doi_ra="Crossref", sources=["crossref"]),
            "r2": RoutePlan(doi_ra="Crossref", sources=["crossref"]),
        }
        engine._fake_query = lambda ref, plan: {
            "r1": {"crossref": (SourceHit(source="crossref", metadata={},
                                          fetched_at="2026-07-22T00:00:00Z"), "hit", None)},
            "r2": {"crossref": (SourceHit(source="crossref", metadata={},
                                          fetched_at="2026-07-22T00:00:00Z"), "hit", None)},
        }.get(ref.id, {})

        refs = self._refs()
        engine._run_with_injected(refs)
        self.assertTrue(state.exists())

        # 第二次跑：state 已有全部结果，应跳过所有网络调用
        calls_before = len(engine._transport._opener.calls)
        result2 = engine._run_with_injected(refs)
        self.assertEqual(calls_before, len(engine._transport._opener.calls))
        self.assertEqual(set(result2.evidences.keys()), {"r1", "r2", "r3"})

    def test_state_file_fingerprint_mismatch_raises(self):
        state = pathlib.Path(self.tmp.name) / "state.json"
        state.write_text(json.dumps({"fingerprint": "stale",
                                      "evidences": {}, "done": []}), encoding="utf-8")
        engine = BatchEngine(self.registry,
                             transport=Transport(user_agent="t",
                                                 opener=FakeOpener([]),
                                                 sleep=lambda s: None),
                             cache=Cache(pathlib.Path(self.tmp.name) / "c.db"),
                             state_path=state)
        with self.assertRaises(RuntimeError) as ctx:
            engine._run_with_injected([Ref(id="x", doi="10.1/a")])
        self.assertIn("指纹", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()

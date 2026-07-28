from __future__ import annotations

import unittest

from paper_shared.datasources.registry import Registry, RegistryError


class TestRegistry(unittest.TestCase):
    def setUp(self):
        self.reg = Registry.load()

    def test_loads_all_nine_sources(self):
        ids = {s.id for s in self.reg.all()}
        self.assertEqual(ids, {"crossref", "openalex", "semantic_scholar", "arxiv",
                               "pubmed", "eric", "doi_ra", "cnki", "wanfang"})

    def test_capability_matrix(self):
        doi_capable = {s.id for s in self.reg.with_capability("lookup_doi")}
        self.assertEqual(doi_capable, {"crossref", "openalex", "semantic_scholar", "pubmed", "arxiv"})
        # 撤稿检测双源冗余：Crossref updated-by（Retraction Watch）+ OpenAlex is_retracted
        self.assertEqual({s.id for s in self.reg.with_capability("retraction")},
                         {"crossref", "openalex"})

    def test_guided_sources_have_no_endpoint(self):
        guided = self.reg.guided_sources()
        self.assertEqual({s.id for s in guided}, {"cnki", "wanfang"})
        for s in guided:
            self.assertIsNone(s.base_url)

    def test_rate_limit_two_tiers(self):
        s2 = self.reg.get("semantic_scholar")
        self.assertEqual(s2.rate_limit["anonymous"]["min_interval_s"], 1.0)
        self.assertEqual(s2.rate_limit["with_credential"]["min_interval_s"], 0.1)
        self.assertEqual(s2.auth["key_env"], "SEMANTIC_SCHOLAR_API_KEY")

    def test_unknown_id_raises(self):
        with self.assertRaises(KeyError):
            self.reg.get("nonexistent")

    def test_validation_rejects_bad_kind(self):
        with self.assertRaises(RegistryError):
            Registry.from_data({"schema_version": 1, "sources": [
                {"id": "x", "name_zh": "X", "kind": "magic", "role": "core"}]})


if __name__ == "__main__":
    unittest.main()

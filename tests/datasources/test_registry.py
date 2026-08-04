from __future__ import annotations

import unittest

from paper_shared.datasources.registry import Registry, RegistryError


class TestRegistry(unittest.TestCase):
    def setUp(self):
        self.reg = Registry.load()

    def test_loads_all_sources(self):
        ids = {s.id for s in self.reg.all()}
        self.assertEqual(ids, {"crossref", "openalex", "semantic_scholar", "arxiv",
                               "pubmed", "eric", "doi_ra", "doi_meta", "cnki", "wanfang"})

    def test_capability_matrix(self):
        doi_capable = {s.id for s in self.reg.with_capability("lookup_doi")}
        # doi_meta：中文 DOI（ISTIC / CNKI）的题录来源，走 DOI 内容协商而非站点接口
        self.assertEqual(doi_capable, {"crossref", "openalex", "semantic_scholar",
                                       "pubmed", "arxiv", "doi_meta"})
        # 撤稿检测三源冗余：Crossref updated-by（Retraction Watch）+ OpenAlex is_retracted
        # + PubMed（pubtype "Retracted Publication" 与 CommentsCorrections RetractionIn）。
        # 医学是撤稿重灾区，而前两源在中文与医学期刊上的覆盖都不如 PubMed。
        self.assertEqual({s.id for s in self.reg.with_capability("retraction")},
                         {"crossref", "openalex", "pubmed"})

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

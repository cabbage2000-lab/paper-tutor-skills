from __future__ import annotations

import unittest

from paper_shared.datasources import models


class TestNormalizeDoi(unittest.TestCase):
    def test_strips_url_prefix_and_lowercases(self):
        self.assertEqual(
            models.normalize_doi("https://doi.org/10.1038/NATURE12373 "),
            "10.1038/nature12373",
        )

    def test_plain_doi_passthrough(self):
        self.assertEqual(models.normalize_doi("10.3969/j.issn.1000-0054.2020.01.001"),
                         "10.3969/j.issn.1000-0054.2020.01.001")


class TestContracts(unittest.TestCase):
    def _evidence(self):
        ref = models.Ref(id="r1", doi="10.1038/nature12373", raw_text="Smith 2013 ...")
        return models.Evidence(
            ref_id="r1",
            input=ref,
            doi_ra="Crossref",
            queries=[models.SourceQuery(source="crossref", query_kind="doi",
                                        outcome="hit", from_cache=True)],
            hits=[models.SourceHit(source="crossref",
                                   metadata={"title": "X", "authors": ["A B"], "year": 2013,
                                             "venue": "Nature", "doi": "10.1038/nature12373",
                                             "type": "journal-article"},
                                   fetched_at="2026-07-22T00:00:00Z")],
        )

    def test_evidence_roundtrip(self):
        ev = self._evidence()
        d = ev.to_dict()
        back = models.Evidence.from_dict(d)
        self.assertEqual(back, ev)
        self.assertEqual(d["queries"][0]["outcome"], "hit")

    def test_error_codes_frozen(self):
        self.assertIn("RATE_LIMITED", models.ERROR_CODES)
        self.assertEqual(len(models.ERROR_CODES), 6)

    def test_batch_result_defaults(self):
        br = models.BatchResult(evidences={}, stats={})
        self.assertEqual(br.network_status, "ok")


if __name__ == "__main__":
    unittest.main()

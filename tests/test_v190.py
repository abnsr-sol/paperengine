"""Tests for the v1.9.0 open-source integration + efficiency wave.

Covers: PPS tortured-phrase trie engine, SPRITE fabrication forensics,
the intel cache layer, --sync-all plumbing, and the rwdb screening index.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from papercheck.checks import CheckContext  # noqa: E402
from papercheck.checks.sprite_engine import run as sprite_run  # noqa: E402
from papercheck.checks.tortured_phrases import build_trie, scan  # noqa: E402
from papercheck.checks.tortured_phrases import run as tp_run  # noqa: E402
from papercheck.ingestion import Document  # noqa: E402
from papercheck.intel import (CURATED_PHRASES, _parse_phrases,  # noqa: E402
                              db_status, load_phrases)
from papercheck.risk import Severity  # noqa: E402
from papercheck.sprite import extract_sprite, sprite_feasible  # noqa: E402

_PAD = "The proposed method improves accuracy over baselines in experiments. " * 40


def _doc(text: str) -> Document:
    return Document(path="t.txt", name="t", text=text, file_type=".txt")


class TestTorturedPhrases(unittest.TestCase):
    def test_trie_scan_finds_phrases(self):
        root = build_trie([("irregular timberland", "random forest"),
                           ("counterfeit consciousness", "artificial intelligence")])
        words = "we apply irregular timberland and counterfeit consciousness models".split()
        hits = scan(words, root)
        found = {t for t, _i, _p in hits}
        self.assertEqual(found, {"irregular timberland", "counterfeit consciousness"})

    def test_engine_flags_three_plus_as_high(self):
        text = ("We study counterfeit consciousness and irregular timberland models. "
                "The bosom malignancy dataset was analyzed using profound learning. ") + _PAD
        findings = tp_run(_doc(text), CheckContext())
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].severity, Severity.HIGH)
        self.assertIn("4 tortured phrases", findings[0].title)

    def test_engine_single_hit_is_low(self):
        text = "This paper uses counterfeit consciousness methods for the task. " + _PAD
        findings = tp_run(_doc(text), CheckContext())
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].severity, Severity.LOW)

    def test_clean_text_no_findings(self):
        findings = tp_run(_doc(_PAD + " Nothing suspicious here at all. "), CheckContext())
        self.assertEqual(findings, [])

    def test_short_doc_skipped(self):
        findings = tp_run(_doc("counterfeit consciousness only"), CheckContext())
        self.assertEqual(findings, [])

    def test_curated_list_loads(self):
        pairs = load_phrases()
        self.assertGreaterEqual(len(pairs), len(CURATED_PHRASES))
        self.assertTrue(all(t != i for t, i in pairs))


class TestSprite(unittest.TestCase):
    def test_feasible_dataset(self):
        self.assertTrue(sprite_feasible(4.0, 1.0, 20, 1, 7))

    def test_impossible_sd(self):
        self.assertFalse(sprite_feasible(3.0, 5.0, 10, 1, 5))

    def test_grim_impossible_mean_deferred(self):
        # 3.48 with N=20 is a GRIM violation, not SPRITE's business
        self.assertTrue(sprite_feasible(3.48, 1.0, 20, 1, 7))

    def test_extractor_apa_order(self):
        text = ("Rated on a 1 to 7 point scale (M = 2.1, SD = 2.9, N = 12).")
        results = extract_sprite(text)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].n, 12)
        self.assertFalse(results[0].feasible)

    def test_extractor_n_before_mean(self):
        text = ("A third measure, N = 200, used a 1 to 5 point scale "
                "(M = 3.5, SD = 1.2).")
        results = extract_sprite(text)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].n, 200)
        self.assertTrue(results[0].feasible)

    def test_engine_critical_on_violation(self):
        text = ("Participants rated items on a 1 to 7 point scale "
                "(M = 2.1, SD = 2.9, N = 12). ") + _PAD
        findings = sprite_run(_doc(text), CheckContext())
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].severity, Severity.CRITICAL)
        self.assertIn("mathematically impossible", findings[0].title)

    def test_engine_info_on_clean_pass(self):
        text = ("Participants rated items on a 1 to 7 point scale "
                "(M = 4.5, SD = 0.5, N = 30). ") + _PAD
        findings = sprite_run(_doc(text), CheckContext())
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].severity, Severity.INFO)


class TestIntelCache(unittest.TestCase):
    def test_parse_phrases_dict_shape(self):
        pairs = _parse_phrases('{"tortured phrase": "intended term", "a b": "c d"}')
        self.assertIn(("tortured phrase", "intended term"), pairs)

    def test_parse_phrases_list_shape(self):
        raw = '[{"tortured": "a b", "intended": "c d"}, ["e f", "g h"]]'
        pairs = _parse_phrases(raw)
        self.assertIn(("a b", "c d"), pairs)
        self.assertIn(("e f", "g h"), pairs)

    def test_parse_phrases_garbage_returns_empty(self):
        self.assertEqual(_parse_phrases("<html>not json</html>"), [])

    def test_db_status_memoized_and_safe(self):
        s1 = db_status()
        s2 = db_status()
        self.assertEqual(s1["tortured_phrases"], s2["tortured_phrases"])
        self.assertGreaterEqual(s1["tortured_phrases"], len(CURATED_PHRASES))
        self.assertIn("retraction_db_source", s1)


class TestRwdbIndex(unittest.TestCase):
    def test_bulk_screening_matches_single(self):
        from papercheck import rwdb
        db = [
            {"title": "deep learning approaches for cancer detection", "year": 2020, "reason": "fabrication"},
            {"title": "random forest classification of satellite imagery", "year": 2018, "reason": "duplicate"},
        ]
        refs = ["Smith (2020) Deep learning approaches for cancer detection in Nature.",
                "Unrelated reference about soil science 2015."]
        single = rwdb.screen_references(refs, db)
        per_ref = rwdb.screen_references_bulk(refs, db)
        self.assertEqual(single[0][2], per_ref[0][0][2])  # same db title match
        self.assertEqual(per_ref[1], [])

    def test_index_cache_hit(self):
        from papercheck import rwdb
        e1, t1, g1 = rwdb.get_screening_index(rwdb.default_cache_path())
        e2, t2, g2 = rwdb.get_screening_index(rwdb.default_cache_path())
        self.assertIs(e1, e2)
        self.assertEqual(len(t1), len(e1))


class TestCliSyncFlag(unittest.TestCase):
    def test_help_lists_sync_all(self):
        import io
        from papercheck.__main__ import main
        try:
            with open(os.devnull, "w") as devnull:
                old = sys.stdout
                sys.stdout = io.StringIO()
                try:
                    main(["--help"])
                except SystemExit:
                    pass
                finally:
                    out = sys.stdout.getvalue()
                    sys.stdout = old
            self.assertIn("--sync-all", out)
        except Exception:
            self.fail("help crashed")


if __name__ == "__main__":
    unittest.main()

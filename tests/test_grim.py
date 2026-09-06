"""Tests for GRIM/GRIMMER: deterministic mean/SD consistency checking."""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from papercheck.grim import (  # noqa: E402
    grim_check, grimmer_check, extract_grim, extract_sd_contexts)
from papercheck.ingestion import load_document  # noqa: E402
from papercheck.checks import ALL_ENGINES, CheckContext  # noqa: E402

_PAD = "We study the effect of training on recall performance across groups. " * 12
_PAD2 = "These findings replicate across sessions and cohorts. " * 12


def _doc(body: str):
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
        f.write(body)
        path = f.name
    try:
        return load_document(path)
    finally:
        os.unlink(path)


class TestGrimMath(unittest.TestCase):
    def test_canonical_wikipedia_example(self):
        # N=20 means k/N ends in .X0 or .X5 at 2dp -> 3.48 impossible
        self.assertFalse(grim_check(3.48, 20, 2))
        self.assertTrue(grim_check(3.45, 20, 2))
        self.assertTrue(grim_check(3.40, 20, 2))

    def test_possible_values(self):
        # 50/12 = 4.1667 -> rounds to 4.17, so possible
        self.assertTrue(grim_check(4.17, 12, 2))
        self.assertTrue(grim_check(5.25, 40, 2))

    def test_impossible_values(self):
        self.assertFalse(grim_check(5.23, 40, 2))   # 209/40 = 5.225
        self.assertFalse(grim_check(3.11, 30, 2))   # 93/30=3.1, 94/30=3.13

    def test_one_decimal_always_granular_enough_or_not(self):
        # N=3, mean=3.3: k/3 -> 1.0, 1.33, 1.67, 2.0 ... 3.3 impossible at 1dp?
        # 10/3 = 3.333 -> '3.3' matches -> possible
        self.assertTrue(grim_check(3.3, 3, 1))

    def test_zero_or_negative_n_is_lenient(self):
        self.assertTrue(grim_check(3.48, 0, 2))


class TestGrimExtraction(unittest.TestCase):
    def test_extract_pairs_mean_with_nearest_n(self):
        text = "Participants (N = 20) completed the inventory. Scoring: M = 3.48, SD = 0.74."
        results = extract_grim(text)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].n, 20)
        self.assertFalse(results[0].possible)

    def test_sd_context_extraction(self):
        text = "N = 20 participants. Results: (M = 3.45, SD = 0.74)."
        ctxs = extract_sd_contexts(text)
        self.assertEqual(len(ctxs), 1)
        self.assertAlmostEqual(ctxs[0][0], 3.45)

    def test_skips_means_without_nearby_n(self):
        text = "The mean was 3.48. No sample size is mentioned anywhere here."
        self.assertEqual(len(extract_grim(text)), 0)


class TestGrimEngine(unittest.TestCase):
    def _engine(self):
        for eng in ALL_ENGINES:
            if getattr(eng, "__module__", "").endswith("grim_engine"):
                return eng
        self.fail("grim engine not registered")

    def test_impossible_mean_flags_high(self):
        doc = _doc(_PAD + "\nMethods. Participants (N = 20) completed the "
                       "inventory. Results. The group scored (M = 3.48, "
                       "SD = 0.74). " + _PAD2)
        finds = self._engine()(doc, CheckContext())
        self.assertTrue(any(f.severity.value == "High" and "GRIM" in f.title
                            for f in finds), finds)

    def test_clean_means_info(self):
        doc = _doc(_PAD + "\nMethods. Participants (N = 20) completed the "
                       "inventory. Results. The group scored (M = 3.45, "
                       "SD = 0.76). " + _PAD2)
        finds = self._engine()(doc, CheckContext())
        self.assertTrue(any(f.severity.value == "Info" for f in finds), finds)
        self.assertFalse(any(f.severity.value == "High" for f in finds))

    def test_short_document_skipped(self):
        doc = _doc("N = 20. M = 3.48, SD = 0.74.")
        self.assertEqual(self._engine()(doc, CheckContext()), [])

    def test_grimmer_conservative(self):
        # consistent pair must never be flagged impossible
        self.assertNotEqual(grimmer_check(5.25, 1.02, 40, 2), False)


if __name__ == "__main__":
    unittest.main()

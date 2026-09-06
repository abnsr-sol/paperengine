"""Tests for the statcheck + UGC-14-word statutory wave."""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from papercheck.statscalc import (extract_results, t_p_two_tailed, f_p, chi2_p,  # noqa: E402
                                  z_p_two_tailed, r_p_two_tailed)
from papercheck.checks.statcheck import run as statcheck_run  # noqa: E402
from papercheck.checks.ugc_14word import run as ugc_run  # noqa: E402
from papercheck.checks import CheckContext  # noqa: E402
from papercheck.ingestion import load_document  # noqa: E402
from papercheck.venues import get_rules, describe  # noqa: E402

_THESIS_LINE = ("This study proposes an adaptive load balancing framework for cloud "
                "datacenters using reinforcement learning with hysteresis control "
                "and pre-registered evaluation. ")


def _write(text: str) -> str:
    fd, path = tempfile.mkstemp(suffix=".txt")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(text)
    return path


class TestStatsCalc(unittest.TestCase):
    def test_distribution_reference_points(self):
        self.assertAlmostEqual(t_p_two_tailed(2.0457, 30), 0.05, places=2)
        self.assertAlmostEqual(f_p(4.17, 2, 27), 0.0266, places=2)
        self.assertAlmostEqual(chi2_p(3.841, 1), 0.05, places=2)
        self.assertAlmostEqual(z_p_two_tailed(1.96), 0.05, places=2)
        self.assertAlmostEqual(r_p_two_tailed(0.38, 30), 0.035, places=2)

    def test_extract_and_recompute(self):
        rs = extract_results("A: t(28) = 2.45, p = .021. B: F(2, 46) = 5.31, p = .008.")
        self.assertEqual(len(rs), 2)
        self.assertLess(rs[0].abs_error, 0.005)
        self.assertLess(rs[1].abs_error, 0.005)

    def test_decision_error_detection(self):
        rs = extract_results("Broken: t(58) = 1.20, p = .04.")
        self.assertEqual(len(rs), 1)
        self.assertTrue(rs[0].decision_error)


class TestStatcheckEngine(unittest.TestCase):
    def _doc_with_stats(self, stats_text: str):
        filler = ("Participants were recruited across three sites with stratified "
                  "randomization and pre-registered analysis. " * 6)
        text = (f"# Study\n\n## Abstract\n{filler}\n\n## Methods\n{filler}\n\n"
                f"## Results\n{stats_text}\n\n## Conclusion\n{filler}\n\n"
                "## References\n[1] Smith, J. (2020). Systems. Journal of Systems, 12(3), 1-20.\n")
        return load_document(_write(text))

    def test_decision_error_is_critical(self):
        doc = self._doc_with_stats("Key: t(58) = 1.20, p = .04.")
        findings = statcheck_run(doc, object())
        self.assertTrue(any(f.severity.value.lower() == "critical" for f in findings),
                        [f.title for f in findings])

    def test_consistent_stats_get_info(self):
        stats = ("A: t(28) = 2.45, p = .021. B: F(2, 46) = 5.31, p = .008. "
                 "C: chi2(1) = 4.32, p = .038. D: r(30) = .38, p = .035. "
                 "E: z = 2.61, p = .009.")
        doc = self._doc_with_stats(stats)
        findings = statcheck_run(doc, object())
        titles = " ".join(f.title.lower() for f in findings)
        self.assertIn("verified", titles)

    def test_short_docs_skipped(self):
        doc = load_document(_write("t(28) = 2.45, p = .021 only."))
        self.assertEqual(statcheck_run(doc, object()), [])


class TestUgc14Word(unittest.TestCase):
    def _ctx(self, corpus_docs):
        return CheckContext(venue=describe("ugc_care"), rules=get_rules("ugc_care"),
                            corpus=corpus_docs, online=False, max_online_checks=0)

    def test_level3_critical_and_core_hit(self):
        body = _THESIS_LINE * 12
        paper = load_document(_write(
            "# Paper\n\n## Abstract\n" + body + "\n\n## Methods\nWe used a randomized design.\n\n"
            "## Results\n" + body + "\n\n## Conclusion\n" + body + "\n\n"
            "## References\n[1] Smith, J. (2020). Systems. Journal of Systems, 12(3), 1-20.\n"))
        thesis = load_document(_write("# Thesis\n" + body * 3))
        findings = ugc_run(paper, self._ctx([thesis]))
        titles = [f.title for f in findings]
        self.assertTrue(any("Level exceeded" in t for t in titles))
        self.assertTrue(any("zero-tolerance" in t for t in titles))

    def test_14word_rule_excludes_short_matches(self):
        # 10-word overlap: below the statutory window, must NOT qualify
        body = _THESIS_LINE * 12
        short = ("adaptive load balancing framework for cloud datacenters using "
                 "reinforcement learning with hysteresis control")  # 13 words
        paper = load_document(_write(
            "# Paper\n\n## Abstract\n" + body + "\n\n## Methods\nThe method differs: " + short + " entirely.\n\n"
            "## Results\nFresh analysis here with novel data and new findings described at length. " * 6 +
            "\n\n## Conclusion\nEntirely new conclusions drawn from new experiments. " * 6 + "\n\n"
            "## References\n[1] Smith, J. (2020). Systems. Journal of Systems, 12(3), 1-20.\n"))
        thesis = load_document(_write("# Thesis\n" + short))
        findings = ugc_run(paper, self._ctx([thesis]))
        self.assertFalse(any("Level exceeded" in f.title for f in findings),
                         [f.title for f in findings])

    def test_no_corpus_is_silent(self):
        doc = load_document(_write("A longer manuscript body goes here. " * 60))
        self.assertEqual(ugc_run(doc, self._ctx([])), [])


if __name__ == "__main__":
    unittest.main()

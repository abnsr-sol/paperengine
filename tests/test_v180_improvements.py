"""Tests for the v1.8.0 improvements wave.

Covers: version consistency, --version flag, readiness-score recalibration
(a realistic messy draft must not score 0), and the new venue presets.
"""
import os
import subprocess
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import papercheck  # noqa: E402
from papercheck.risk import RiskReport, Finding, Severity  # noqa: E402
from papercheck.venues import list_venues, get_rules  # noqa: E402


def _finding(sev, conf):
    return Finding(category="Test", severity=sev, title="t", detail="d",
                   evidence="e", action="a", confidence=conf)


class TestVersionConsistency(unittest.TestCase):
    def test_dunder_version_matches_pyproject(self):
        import re
        pyproject = os.path.join(os.path.dirname(__file__), "..", "pyproject.toml")
        with open(pyproject, encoding="utf-8") as fh:
            m = re.search(r'^version\s*=\s*"([^"]+)"', fh.read(), re.MULTILINE)
        self.assertIsNotNone(m)
        self.assertEqual(papercheck.__version__, m.group(1),
                         "__init__.__version__ must match pyproject.toml")

    def test_version_flag(self):
        r = subprocess.run(
            [sys.executable, "-m", "papercheck", "--version"],
            capture_output=True, text=True, timeout=60,
        )
        self.assertEqual(r.returncode, 0)
        self.assertIn(papercheck.__version__, r.stdout)


class TestScoreRecalibration(unittest.TestCase):
    def test_realistic_messy_draft_does_not_score_zero(self):
        """20 medium + 10 high + 15 low at conf 0.7 — a normal real draft.
        The old saturation curves zeroed exactly this profile."""
        rep = RiskReport(document_name="x", venue="v")
        for _ in range(20):
            rep.add(_finding(Severity.MEDIUM, 0.7))
        for _ in range(10):
            rep.add(_finding(Severity.HIGH, 0.7))
        for _ in range(15):
            rep.add(_finding(Severity.LOW, 0.7))
        self.assertGreater(rep.readiness_score, 45,
                           "a draft with no criticals must not be unscoreable")

    def test_criticals_still_brutal(self):
        rep = RiskReport(document_name="x", venue="v")
        for _ in range(2):
            rep.add(_finding(Severity.CRITICAL, 0.95))
        self.assertLess(rep.readiness_score, 65)


class TestNewVenuePresets(unittest.TestCase):
    def test_new_international_presets_exist(self):
        intl = list_venues()["international"]
        for name in ("lncs_springer", "science_journal", "medical_journal",
                     "cell_journal", "arxiv_preprint"):
            self.assertIn(name, intl, f"{name} missing from international presets")

    def test_total_venue_count_grew(self):
        v = list_venues()
        self.assertGreaterEqual(len(v["international"]) + len(v["national"]), 23)

    def test_preset_rules_resolve(self):
        r = get_rules("science_journal")
        self.assertEqual(r["abstract_word_limit"], 125)
        self.assertEqual(r["publisher"], "AAAS")
        r = get_rules("medical_journal")
        self.assertTrue(r.get("double_blind"))
        r = get_rules("lncs_springer")
        self.assertEqual(r["page_limit"], 16)


if __name__ == "__main__":
    unittest.main()

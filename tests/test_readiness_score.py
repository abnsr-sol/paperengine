"""Tests for the readiness score calibration."""
import unittest
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from papercheck.risk import RiskReport, Finding, Severity


def _finding(sev, conf):
    return Finding(category="Test", severity=sev, title="t", detail="d", evidence="e", action="a", confidence=conf)


class TestReadinessScore(unittest.TestCase):
    def test_clean_report_scores_100(self):
        rep = RiskReport(document_name="x", venue="v")
        self.assertEqual(rep.readiness_score, 100)

    def test_low_severity_tail_cannot_zero_score(self):
        rep = RiskReport(document_name="x", venue="v")
        for i in range(30):
            rep.add(_finding(Severity.LOW, 0.9))
        self.assertGreater(rep.readiness_score, 40)

    def test_critical_lowers_score_sharply(self):
        rep = RiskReport(document_name="x", venue="v")
        rep.add(_finding(Severity.CRITICAL, 0.95))
        self.assertLess(rep.readiness_score, 90)
        self.assertGreater(rep.readiness_score, 60)
        # multiple criticals push below 60
        for _ in range(2):
            rep.add(_finding(Severity.CRITICAL, 0.95))
        self.assertLess(rep.readiness_score, 60)

    def test_severity_ordering(self):
        light = RiskReport(document_name="x", venue="v")
        light.add(_finding(Severity.LOW, 0.9))
        heavy = RiskReport(document_name="x", venue="v")
        heavy.add(_finding(Severity.CRITICAL, 0.95))
        self.assertGreater(light.readiness_score, heavy.readiness_score)

    def test_score_bounded(self):
        rep = RiskReport(document_name="x", venue="v")
        for i in range(50):
            rep.add(_finding(Severity.CRITICAL, 1.0))
            rep.add(_finding(Severity.HIGH, 1.0))
        self.assertGreaterEqual(rep.readiness_score, 0)
        self.assertLessEqual(rep.readiness_score, 100)


if __name__ == '__main__':
    unittest.main()
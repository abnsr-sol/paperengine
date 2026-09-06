"""Tests for fixplan and peer_review engines."""
import unittest
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from papercheck.ingestion import Document
from papercheck.risk import RiskReport, Finding, Severity
from papercheck.fixplan import build_fix_plan, render_fix_plan
from papercheck.checks import peer_review


def _doc(text):
    return Document(path='x', name='x', file_type='txt', text=text, references=[])


def _finding(sev, title, action="Do the fix."):
    return Finding(category="Test", severity=sev, title=title, detail="d", evidence="e", action=action, confidence=0.8)


class TestFixPlan(unittest.TestCase):
    def test_orders_by_severity(self):
        rep = RiskReport(document_name="x", venue="v")
        rep.add(_finding(Severity.LOW, "Minor issue"))
        rep.add(_finding(Severity.CRITICAL, "Fatal flaw"))
        steps = build_fix_plan(rep)
        self.assertEqual(steps[0].title, "Fatal flaw")
        self.assertEqual(steps[0].order, 1)

    def test_dedup_same_title(self):
        rep = RiskReport(document_name="x", venue="v")
        rep.add(_finding(Severity.HIGH, "No ORCID iD found"))
        rep.add(_finding(Severity.HIGH, "No ORCID iD found"))
        steps = build_fix_plan(rep)
        self.assertEqual(len(steps), 1)

    def test_estimated_effort_present(self):
        rep = RiskReport(document_name="x", venue="v")
        rep.add(_finding(Severity.MEDIUM, "Issue one"))
        steps = build_fix_plan(rep)
        self.assertIn(steps[0].effort, {"5 min", "30 min", "1-2 h", "2+ h"})

    def test_render_contains_header(self):
        rep = RiskReport(document_name="x", venue="v")
        rep.add(_finding(Severity.HIGH, "Issue one"))
        text = render_fix_plan(rep)
        self.assertIn("PRE-SUBMISSION FIX PLAN", text)
        self.assertIn("Issue one", text)

    def test_empty_report(self):
        rep = RiskReport(document_name="x", venue="v")
        self.assertIn("clean", render_fix_plan(rep))


class TestPeerReview(unittest.TestCase):
    def test_coerced_citations(self):
        d = _doc("Response to Reviewers\nReviewer #1: You should cite the following references [1][2][3].\n"
                 "Reviewer #2: Please cite recent work [4][5][6].")
        out = peer_review.run(d, None)
        self.assertTrue(any('coerced citations' in f.title for f in out))

    def test_pressure_language(self):
        out = peer_review.run(_doc("Response to Reviewers. We were forced to add these to satisfy the reviewer."), None)
        self.assertTrue(any('Pressure-to-cite' in f.title for f in out))

    def test_freemail_reviewers(self):
        out = peer_review.run(_doc("Suggested reviewers: Dr Jane Doe (janedoe@gmail.com)."), None)
        self.assertTrue(any('free-mail' in f.title for f in out))

    def test_same_domain_reviewer(self):
        out = peer_review.run(_doc("From: author@university.edu\nSuggested reviewers: Dr Big Name (bname@university.edu)."), None)
        self.assertTrue(any("authors' domain" in f.title for f in out))

    def test_clean_response(self):
        out = peer_review.run(_doc("Response to Reviewers. We thank the reviewer and revised accordingly."), None)
        self.assertEqual(out, [])


if __name__ == '__main__':
    unittest.main()
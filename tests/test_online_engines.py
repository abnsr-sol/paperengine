"""Tests for the latest engines: scope_match, rebuttal, literature_search (offline path)."""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from papercheck.ingestion import Document
from papercheck.venues import get_rules, describe
from papercheck.checks import CheckContext
from papercheck.checks.scope_match import run as scope_run
from papercheck.checks.rebuttal import run as rebuttal_run
from papercheck.checks.literature_search import run as lit_run


def _doc(text, paras=None):
    return Document(path="t.txt", name="t.txt", file_type="txt",
                    text=text, paragraphs=paras or [text])


class TestScopeMatch(unittest.TestCase):
    def test_mismatch_flags_for_medical_venue(self):
        text = ("Quantum chromodynamics lattice simulations of gauge fields with "
                "topological defects and string theory dualities. ") * 6
        ctx = CheckContext(venue=describe("ugc_care"), rules=get_rules("ugc_care"))
        fs = scope_run(_doc(text), ctx)
        self.assertTrue(any("scope" in f.title.lower() for f in fs))

    def test_fit_no_flag(self):
        text = ("A study of engineering education methods for technology students "
                "with a survey of management practices in science departments. ") * 6
        ctx = CheckContext(venue=describe("ugc_care"), rules=get_rules("ugc_care"))
        fs = scope_run(_doc(text), ctx)
        self.assertFalse(any(f.severity.value == "Medium" for f in fs))


class TestRebuttal(unittest.TestCase):
    def test_response_letter_analyzed(self):
        text = ("Response to Reviewers.\n\nReviewer 1:\nComment 1: The sample is small.\n"
                "Response: We thank the reviewer. We have added new experiments with 200 subjects "
                "and revised the limitations section.\n"
                "Reviewer 2:\nComment 1: The reviewer is wrong about our method.\n"
                "Response: We disagree strongly with this comment. ") * 2
        fs = rebuttal_run(_doc(text), CheckContext(rules=get_rules("generic")))
        titles = " | ".join(f.title for f in fs)
        self.assertIn("Defensive tone", titles)

    def test_manuscript_not_flagged(self):
        text = ("We propose a framework for classification. The model was evaluated "
                "on three benchmarks with strong results. ") * 6
        fs = rebuttal_run(_doc(text), CheckContext(rules=get_rules("generic")))
        self.assertEqual(fs, [])


class TestLiteratureSearchOffline(unittest.TestCase):
    def test_offline_returns_nothing(self):
        text = "Landmark-guided vision mamba for deepfake detection. " * 10
        ctx = CheckContext(rules=get_rules("generic"), online=False)
        fs = lit_run(_doc(text), ctx)
        self.assertEqual(fs, [])


if __name__ == "__main__":
    unittest.main()

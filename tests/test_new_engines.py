"""Tests for the engines added in the expansion: methodology, reporting_guidelines, writing_depth, legal_ethics."""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from papercheck.ingestion import Document
from papercheck.risk import Severity
from papercheck.venues import get_rules
from papercheck.checks import CheckContext
from papercheck.checks.methodology import run as methodology_run
from papercheck.checks.reporting_guidelines import run as reporting_run
from papercheck.checks.writing_depth import run as writing_run
from papercheck.checks.legal_ethics import run as legal_run


def _doc(text, paras=None):
    return Document(path="t.txt", name="t.txt", file_type="txt",
                    text=text, paragraphs=paras or [text])


class TestMethodology(unittest.TestCase):
    def test_clinical_without_ethics_flags(self):
        text = ("We conducted a randomized controlled trial with 120 patients. "
                "Patients were recruited from a university hospital cohort. ") * 5
        fs = methodology_run(_doc(text), CheckContext(rules=get_rules("generic")))
        titles = " | ".join(f.title for f in fs)
        self.assertIn("ethics approval", titles.lower())
        self.assertIn("informed-consent", titles.lower())

    def test_clinical_with_ethics_passes(self):
        text = ("This randomized trial enrolled 120 patients after ethics committee "
                "approval (IRB-2023-045). Written informed consent was obtained from "
                "all participants; randomization was computer-generated and outcome "
                "assessors were blinded. The trial was registered at ClinicalTrials.gov "
                "(NCT01234567).") * 4
        fs = methodology_run(_doc(text), CheckContext(rules=get_rules("generic")))
        self.assertEqual(fs, [])

    def test_ml_paper_without_ablation_flags(self):
        text = ("We propose a novel deep framework for detection. Our model uses a "
                "transformer backbone with a custom attention module. ") * 8
        # NOTE: ablation + baseline-comparison checks are owned by the
        # `reproducibility` engine (single ownership; methodology's copies
        # were removed in the duplicate-findings fix).
        from papercheck.checks.reproducibility import run as repro_run
        fs = repro_run(_doc(text), CheckContext(rules=get_rules("generic")))
        titles = " | ".join(f.title for f in fs)
        self.assertIn("baseline comparison", titles.lower())
        self.assertIn("ablation", titles.lower())


class TestReportingGuidelines(unittest.TestCase):
    def test_rct_missing_consort_items(self):
        text = ("We conducted a randomized controlled trial comparing drug A and "
                "placebo. ") * 6
        fs = reporting_run(_doc(text), CheckContext(rules=get_rules("generic")))
        titles = " | ".join(f.title for f in fs)
        self.assertIn("flow diagram", titles.lower())
        self.assertIn("registration", titles.lower())

    def test_review_missing_prospero(self):
        text = ("We performed a systematic review and meta-analysis of cohort studies. "
                "We searched PubMed and Web of Science using a predefined string. ") * 6
        fs = reporting_run(_doc(text), CheckContext(rules=get_rules("generic")))
        titles = " | ".join(f.title for f in fs)
        self.assertIn("PROSPERO", titles)


class TestWritingDepth(unittest.TestCase):
    def test_weasel_words_flag(self):
        text = ("Clearly, this approach is obviously better and importantly it "
                "undoubtedly works quite well. Evidently the results are simply "
                "excellent and arguably the best. ") * 2
        fs = writing_run(_doc(text), CheckContext(rules=get_rules("generic")))
        self.assertTrue(any("weasel" in f.title.lower() for f in fs))

    def test_clean_text_no_flags(self):
        text = ("The model was evaluated on three benchmarks. Accuracy improved "
                "from 0.71 to 0.84. We report error bars as standard deviation. ") * 4
        fs = writing_run(_doc(text), CheckContext(rules=get_rules("generic")))
        self.assertFalse(any("weasel" in f.title.lower() for f in fs))


class TestLegalEthics(unittest.TestCase):
    def test_adapted_without_permission_flags(self):
        text = ("Figure 2 was adapted from Smith et al. The figure shows the "
                "proposed architecture. ") * 5
        fs = legal_run(_doc(text), CheckContext(rules=get_rules("generic")))
        self.assertTrue(any("permission" in f.title.lower() for f in fs))

    def test_dual_use_without_statement(self):
        text = ("We engineered a novel pathogen strain using CRISPR and a toxin "
                "expression system. ") * 5
        fs = legal_run(_doc(text), CheckContext(rules=get_rules("generic")))
        self.assertTrue(any("dual-use" in f.title.lower() for f in fs))

    def test_clean_text_no_flags(self):
        text = ("We present a framework for image classification. All data were "
                "obtained from public benchmarks. ") * 4
        fs = legal_run(_doc(text), CheckContext(rules=get_rules("generic")))
        self.assertEqual(fs, [])


if __name__ == "__main__":
    unittest.main()

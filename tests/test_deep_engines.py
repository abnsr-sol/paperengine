"""Tests for the deep-analysis engines: stats_deep, design_claims, redundancy, domain_checklists."""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from papercheck.ingestion import Document, Section
from papercheck.venues import get_rules
from papercheck.checks import CheckContext
from papercheck.checks.stats_deep import run as stats_deep_run
from papercheck.checks.design_claims import run as design_run
from papercheck.checks.redundancy import run as redundancy_run
from papercheck.checks.domain_checklists import run as domain_run


def _doc(text, sections=None, paras=None):
    return Document(path="t.txt", name="t.txt", file_type="txt",
                    text=text, paragraphs=paras or [text], sections=sections or [])


class TestStatsDeep(unittest.TestCase):
    def test_survival_without_censoring(self):
        text = ("We plotted Kaplan-Meier survival curves and compared groups with "
                "the log-rank test; the hazard ratio was 1.8. ") * 5
        fs = stats_deep_run(_doc(text), CheckContext(rules=get_rules("generic")))
        self.assertTrue(any("censoring" in f.title.lower() for f in fs))

    def test_bayesian_without_prior(self):
        text = ("We used a Bayesian model with MCMC sampling and report posterior "
                "estimates for all parameters. ") * 5
        fs = stats_deep_run(_doc(text), CheckContext(rules=get_rules("generic")))
        self.assertTrue(any("prior" in f.title.lower() for f in fs))

    def test_p_clustering(self):
        text = ("Results: p=0.041, p=0.043, p=0.047, p=0.048, p=0.049 across five "
                "tests. ") * 3
        fs = stats_deep_run(_doc(text), CheckContext(rules=get_rules("generic")))
        self.assertTrue(any("clustering" in f.title.lower() for f in fs))


class TestDesignClaims(unittest.TestCase):
    def test_causal_claim_from_observational(self):
        text = ("This cross-sectional cohort study shows that smoking causes "
                "lung damage and improves recovery. ") * 6
        fs = design_run(_doc(text), CheckContext(rules=get_rules("generic")))
        self.assertTrue(any("causal" in f.title.lower() for f in fs))

    def test_clean_text_no_flags(self):
        text = ("We conducted a randomized controlled trial. The intervention was "
                "associated with improved outcomes (p=0.02). ") * 5
        fs = design_run(_doc(text), CheckContext(rules=get_rules("generic")))
        self.assertFalse(any("causal" in f.title.lower() for f in fs))


class TestRedundancy(unittest.TestCase):
    def test_abstract_conclusion_overlap(self):
        shared = ("The proposed framework detects deepfakes using frequency "
                  "analysis and temporal modeling across generators. ")
        sections = [
            Section(heading="Abstract", level=1, body=shared * 3, start_index=0),
            Section(heading="Conclusion", level=1, body=shared * 3 + "Future work remains.",
                    start_index=100),
        ]
        fs = redundancy_run(_doc(shared * 6, sections), CheckContext(rules=get_rules("generic")))
        self.assertTrue(any("repeats" in f.title.lower() for f in fs))


class TestDomainChecklists(unittest.TestCase):
    def test_diagnostic_missing_standard(self):
        text = ("We assessed diagnostic accuracy of the test. Sensitivity and "
                "specificity were reported. ") * 6
        fs = domain_run(_doc(text), CheckContext(rules=get_rules("generic")))
        self.assertTrue(any("reference standard" in f.title.lower() for f in fs))

    def test_qualitative_missing_reflexivity(self):
        text = ("We conducted a qualitative study using semi-structured interviews "
                "and thematic analysis. ") * 6
        fs = domain_run(_doc(text), CheckContext(rules=get_rules("generic")))
        self.assertTrue(any("reflexivity" in f.title.lower() for f in fs))


if __name__ == "__main__":
    unittest.main()

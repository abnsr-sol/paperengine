"""Tests for the v1.10.0 standards wave: asa_pvalues, power_adequacy,
engineering_vv, country_standards, and the 13-family EQUATOR expansion.
"""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from papercheck.ingestion import Document, Section
from papercheck.checks import ALL_ENGINES
from papercheck.checks.asa_pvalues import run as asa_run
from papercheck.checks.power_adequacy import run as power_run
from papercheck.checks.engineering_vv import run as engvv_run
from papercheck.checks.country_standards import run as country_run
from papercheck.checks.reporting_guidelines import run as reporting_run


FILL = ("The background of this work spans several areas of applied research "
        "and prior studies have examined related questions in depth over many "
        "years of careful investigation by multiple groups. ")


def _doc(text):
    full = FILL * 12 + " " + text
    return Document(path="t.txt", name="t.txt", file_type="txt", text=full,
                    paragraphs=[full],
                    sections=[Section("Introduction", 1, full, 0)])


class TestRegistration(unittest.TestCase):
    def test_80_engines_no_duplicates(self):
        names = [getattr(e, "__module__", "?").rsplit(".", 1)[-1] for e in ALL_ENGINES]
        self.assertEqual(len(names), len(set(names)))
        self.assertGreaterEqual(len(ALL_ENGINES), 80)
        for mod in ("asa_pvalues", "power_adequacy", "engineering_vv", "country_standards", "tiva_engine", "pcurve_engine"):
            self.assertIn(mod, names)


class TestASAPValues(unittest.TestCase):
    def test_silent_without_p_values(self):
        fs = asa_run(_doc("A plain methods paper with no statistics at all. " * 10), None)
        self.assertEqual(fs, [])

    def test_p3_no_effect_size(self):
        text = ("The treatment effect was statistically significant (p < 0.05) "
                "and the intervention outperformed control. " * 4)
        fs = asa_run(_doc(text), None)
        self.assertTrue(any("principle 3" in f.title for f in fs))

    def test_p3_passes_with_effect_size(self):
        text = ("The difference was significant (p = 0.012) with a large effect "
                "size, Cohen's d = 0.91, 95% CI [0.4, 1.4]. " * 4)
        fs = asa_run(_doc(text), None)
        self.assertFalse(any("principle 3" in f.title for f in fs))

    def test_p4_magnitude_rhetoric(self):
        text = ("The result was highly significant (p < 0.001) across cohorts. " * 4)
        fs = asa_run(_doc(text), None)
        self.assertTrue(any("principle 4" in f.title for f in fs))

    def test_p5_nonsignificance_as_no_effect(self):
        text = ("The comparison was not significant (p = 0.21), therefore no "
                "difference exists between the groups. " * 4)
        fs = asa_run(_doc(text), None)
        self.assertTrue(any("principle 5" in f.title for f in fs))

    def test_p6_euphemism(self):
        text = ("The effect was marginally significant (p = 0.058) in this "
                "sample of participants. " * 4)
        fs = asa_run(_doc(text), None)
        self.assertTrue(any("principle 6" in f.title for f in fs))

    def test_finding_fields_well_typed(self):
        text = ("The result was highly significant (p < 0.001). " * 6)
        for f in asa_run(_doc(text), None):
            self.assertIsInstance(f.confidence, float)
            self.assertEqual(f.source, "asa_pvalues")
            self.assertTrue(f.action)


class TestPowerAdequacy(unittest.TestCase):
    def test_silent_without_human_subjects(self):
        fs = power_run(_doc("We analyzed 50,000 images from a benchmark corpus. " * 8), None)
        self.assertEqual(fs, [])

    def test_no_power_language(self):
        text = ("Participants were recruited from three clinics and completed "
                "the survey battery in a single session. " * 4)
        fs = power_run(_doc(text), None)
        self.assertTrue(any("sample-size justification" in f.title for f in fs))

    def test_passes_with_power_analysis(self):
        text = ("Participants were recruited after an a priori power analysis "
                "(G*Power 3.1; f = 0.25, alpha = 0.05, power = 0.80) indicated "
                "n = 128 per arm. " * 4)
        fs = power_run(_doc(text), None)
        self.assertFalse(any("sample-size justification" in f.title for f in fs))

    def test_small_n_with_robust_claim(self):
        text = ("Participants (n = 12 per group) completed the protocol and the "
                "results provide robust evidence for the mechanism. " * 4)
        fs = power_run(_doc(text), None)
        self.assertTrue(any("high-certainty" in f.title for f in fs))

    def test_unexplained_imbalance_after_randomization(self):
        text = ("Patients were randomly assigned to the two arms (n = 55 and "
                "n = 18) and completed the six-month follow-up assessment. " * 4)
        fs = power_run(_doc(text), None)
        self.assertTrue(any("group sizes differ" in f.title.lower() for f in fs))


class TestEngineeringVV(unittest.TestCase):
    def test_silent_without_simulation(self):
        fs = engvv_run(_doc("A survey-based study of practitioner attitudes. " * 12), None)
        self.assertEqual(fs, [])

    def test_full_vv_story_passes(self):
        text = (
            "Finite element analysis was performed in Abaqus 2024. "
            "A mesh independence study compared three refinements with a grid "
            "convergence index below 2%. "
            "Boundary conditions were applied: fixed support at the base and a "
            "prescribed displacement at the loading face. "
            "Validation against experimental strain-gauge data showed agreement "
            "within 4%. "
            "An uncertainty quantification with Monte Carlo propagation of "
            "input variability is reported. "
            "Material properties were taken from the ASTM standard datasheet. "
            "Computation ran on an Intel Xeon with 64 GB RAM. "
        ) * 2
        fs = engvv_run(_doc(text), None)
        self.assertEqual(fs, [])

    def test_bare_simulation_flags_all(self):
        text = ("Finite element analysis of the bracket was performed. Mesh was "
                "generated. Maximum stress was 245 MPa. " * 3)
        fs = engvv_run(_doc(text), None)
        titles = " | ".join(f.title for f in fs)
        self.assertIn("independence", titles)
        self.assertIn("validation", titles.lower())
        self.assertIn("Boundary conditions", titles)
        self.assertIn("uncertainty", titles.lower())


class TestCountryStandards(unittest.TestCase):
    def test_silent_without_funders(self):
        fs = country_run(_doc("An unfunded independent study by the authors. " * 10), None)
        self.assertEqual(fs, [])

    def test_india_ugc(self):
        text = ("This work was supported by the University Grants Commission "
                "(UGC) under a major research project. " * 3)
        fs = country_run(_doc(text), None)
        self.assertTrue(any("Indian funder" in f.title for f in fs))

    def test_us_nelson_missing_oa(self):
        text = ("Funded by the National Science Foundation award 2345678. " * 4)
        fs = country_run(_doc(text), None)
        self.assertTrue(any("Nelson Memo" in f.title for f in fs))

    def test_us_nelson_passes_with_oa_and_data(self):
        text = ("Funded by the National Science Foundation award 2345678. "
                "All data are deposited in an open repository under a Creative "
                "Commons licence and the accepted manuscript will be open "
                "access. Data sharing follows the funder plan. " * 3)
        fs = country_run(_doc(text), None)
        self.assertFalse(any("Nelson Memo" in f.title for f in fs))

    def test_eu_plan_s(self):
        text = ("Funded by the European Research Council (ERC) Starting Grant "
                "101040221. " * 4)
        fs = country_run(_doc(text), None)
        self.assertTrue(any("Rights Retention" in f.title for f in fs))

    def test_japan_and_korea(self):
        jp = country_run(_doc("Supported by JSPS KAKENHI grant 21K01234. " * 4), None)
        kr = country_run(_doc("Supported by the National Research Foundation of Korea grant 2021R1A2C. " * 4), None)
        self.assertTrue(any("Japanese funder" in f.title for f in jp))
        self.assertTrue(any("Korean funder" in f.title for f in kr))


class TestReportingGuidelinesExpansion(unittest.TestCase):
    def test_consort_still_works(self):
        fs = reporting_run(_doc("A randomized controlled trial of drug X in adults. " * 6), None)
        self.assertTrue(any("CONSORT" in f.title and not f.title.startswith("CONSORT-AI") for f in fs))

    def test_tripod(self):
        fs = reporting_run(_doc("We built a prediction model with machine learning to predict 30-day readmission; AUROC 0.84. " * 4), None)
        self.assertTrue(any("TRIPOD" in f.title for f in fs))

    def test_stard(self):
        fs = reporting_run(_doc("A diagnostic accuracy study of the index test versus the reference standard; sensitivity and specificity computed. " * 4), None)
        self.assertTrue(any("STARD" in f.title for f in fs))

    def test_cheers(self):
        fs = reporting_run(_doc("A cost-effectiveness analysis reporting cost per QALY and the ICER. " * 4), None)
        self.assertTrue(any("CHEERS" in f.title for f in fs))

    def test_miqe(self):
        fs = reporting_run(_doc("RT-qPCR quantified expression; GAPDH was the housekeeping gene; the 2 delta delta Ct method was applied. " * 4), None)
        self.assertTrue(any("MIQE" in f.title for f in fs))

    def test_care_and_srqr(self):
        care = reporting_run(_doc("We report a case of the rare presentation in this patient. " * 4), None)
        qual = reporting_run(_doc("A qualitative study using semi-structured interviews with thematic analysis. " * 4), None)
        self.assertTrue(any("CARE" in f.title for f in care))
        self.assertTrue(any("SRQR" in f.title for f in qual))

    def test_plain_paper_no_consort(self):
        fs = reporting_run(_doc("A software engineering evaluation of build systems across repositories. " * 10), None)
        self.assertEqual([f for f in fs if "CONSORT" in f.title or "PRISMA" in f.title], [])


if __name__ == "__main__":
    unittest.main()

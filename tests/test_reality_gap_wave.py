"""Tests for the 2026-10-12 reality-gap wave: ref_forensics, topic_coherence,
rationale, and the scope_match default-venue fix.

Each test is anchored to a documented rejection/retraction finding:

* ref_forensics   -> fabricated references: 1-in-277 papers in 2026 (Lancet
                      audit of 97.1M references) and 7.54% of retractions
* topic_coherence -> title/abstract fit: the #1 desk-rejection reason
                      (35% of desk rejects, Wu 2024; Menon 2020, n=898)
* rationale       -> weak study rationale: a top-3 post-review rejection
                      reason (Menon 2020); "importance of the findings"
                      (Edmans 2025, 1,000 rejections)
* scope_match     -> scope is the top desk-reject reason, yet the default
                      `papercheck paper.docx` run performed no scope check
"""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from papercheck.ingestion import Document, _annotate_structure
from papercheck.risk import Severity
from papercheck.venues import describe, get_rules
from papercheck.checks import ALL_ENGINES, CheckContext
from papercheck.checks.ref_forensics import run as ref_forensics_run
from papercheck.checks.topic_coherence import run as topic_run
from papercheck.checks.rationale import run as rationale_run
from papercheck.checks.scope_match import run as scope_run


def _doc(text, with_sections=True):
    d = Document(path="t.txt", name="t.txt", file_type="txt", text=text,
                 paragraphs=[p for p in text.split("\n") if p.strip()])
    if with_sections:
        _annotate_structure(d)
    return d


def _ref_doc(refs):
    body = "Prior work established this [1,2,3,4,5,6]. " * 20
    text = body + "\nReferences\n" + "\n".join(refs)
    return Document(path="t.txt", name="t.txt", file_type="txt", text=text,
                    references=refs)


# Shared prose so length guards (>250-word body) are satisfied honestly.
_INTRO = ("Fertilizer application rates were varied across plots. Soil moisture "
          "was recorded weekly. Rainfall was measured at the station. Nutrient "
          "concentrations were assayed in the laboratory. Crop yield was weighed "
          "at harvest. Nitrogen levels were logged daily. ")
_METHODS = ("Plots received treatments of 0, 50 and 100 kg per hectare. Moisture "
            "was sampled at ten depths. Yield was measured by combine harvester. "
            "Statistics were computed in R. Replicates were randomised across the "
            "field. Blocks were stratified by soil type. ")
_RESULTS = ("Yield increased by 8 percent at 50 kg per hectare. Soil moisture "
            "declined through the season. Nitrogen leaching was observed in the "
            "plots. Rainfall explained most of the variance across the sites.")


class TestRefForensics(unittest.TestCase):
    """Offline fabricated-reference detection — the gap the Lancet audit exposed."""

    def test_future_dated_reference_is_high(self):
        refs = ["[1] A. Smith. Nature 599, 120-135 (2031).",
                "[2] J. Doe. Science 380, 1-4 (2022).",
                "[3] K. Lee. Lancet 401, 88-95 (2023).",
                "[4] M. Ali. PLOS ONE 19, e0280001 (2024).",
                "[5] S. Rao. J Adv Res 12, 1-9 (2020).",
                "[6] P. Kumar. IEEE TPAMI 45, 100-112 (2023)."]
        fs = ref_forensics_run(_ref_doc(refs), CheckContext())
        hit = [f for f in fs if "future" in f.title.lower()]
        self.assertTrue(hit, "a citation dated in the future must be flagged")
        self.assertEqual(hit[0].severity, Severity.HIGH)
        self.assertIn("2031", hit[0].evidence)

    def test_backwards_page_range_is_high(self):
        refs = ["[1] A. Smith. Nature 599, 120-135 (2021).",
                "[2] J. Doe. Science 380, 1-4 (2022).",
                "[3] K. Lee. Lancet 401, 88-55 (2025).",
                "[4] M. Ali. PLOS ONE 19, e0280001 (2024).",
                "[5] S. Rao. J Adv Res 12, 1-9 (2020).",
                "[6] P. Kumar. IEEE TPAMI 45, 100-112 (2023)."]
        fs = ref_forensics_run(_ref_doc(refs), CheckContext())
        hit = [f for f in fs if "backwards" in f.title.lower()]
        self.assertTrue(hit, "88-55 must be flagged")
        self.assertIn("88-55", hit[0].evidence)

    def test_clean_references_are_silent(self):
        refs = ["[1] A. Smith, B. Jones. Nature 599, 120-135 (2021).",
                "[2] J. Doe. Science 380, 1-4 (2022).",
                "[3] K. Lee, R. Patel. Lancet 401, 88-95 (2023).",
                "[4] M. Ali. PLOS ONE 19, e0280001 (2024). doi:10.1371/journal.pone.0280001",
                "[5] S. Rao. J Adv Res 12(3), 1-9 (2020).",
                "[6] P. Kumar. IEEE TPAMI 45, 100-112 (2023)."]
        self.assertEqual(ref_forensics_run(_ref_doc(refs), CheckContext()), [])

    def test_doi_page_span_is_not_a_page_range(self):
        """A DOI like 10.1111/j.1467-8691.2019 must not read as pages 1467-8691."""
        refs = ["[1] A. Smith. J Pers Soc Psychol 116, 1-20 (2019). "
                "doi:10.1111/j.1467-8691.2019.01234.x",
                "[2] J. Doe. Science 380, 1-4 (2022).",
                "[3] K. Lee. Lancet 401, 88-95 (2023).",
                "[4] M. Ali. PLOS ONE 19, e0280001 (2024).",
                "[5] S. Rao. J Adv Res 12, 1-9 (2020).",
                "[6] P. Kumar. IEEE TPAMI 45, 100-112 (2023)."]
        fs = ref_forensics_run(_ref_doc(refs), CheckContext())
        self.assertFalse([f for f in fs if "backwards" in f.title.lower()],
                         "DOI suffixes are not page ranges")

    def test_duplicate_doi_across_references(self):
        refs = ["[1] A. Smith. Nature 599, 120-135 (2021). doi:10.1038/s41586-021-0001-x",
                "[2] B. Jones. Science 380, 1-4 (2022). doi:10.1038/s41586-021-0001-x",
                "[3] K. Lee. Lancet 401, 88-95 (2023).",
                "[4] M. Ali. PLOS ONE 19, e0280001 (2024).",
                "[5] S. Rao. J Adv Res 12, 1-9 (2020).",
                "[6] P. Kumar. IEEE TPAMI 45, 100-112 (2023)."]
        fs = ref_forensics_run(_ref_doc(refs), CheckContext())
        self.assertTrue([f for f in fs if "Same DOI" in f.title])

    def test_malformed_doi_flagged(self):
        refs = ["[1] A. Smith. Nature 599, 120-135 (2021). doi:10.1371",
                "[2] J. Doe. Science 380, 1-4 (2022).",
                "[3] K. Lee. Lancet 401, 88-95 (2023).",
                "[4] M. Ali. PLOS ONE 19, e0280001 (2024).",
                "[5] S. Rao. J Adv Res 12, 1-9 (2020).",
                "[6] P. Kumar. IEEE TPAMI 45, 100-112 (2023)."]
        fs = ref_forensics_run(_ref_doc(refs), CheckContext())
        self.assertTrue([f for f in fs if "Malformed DOI" in f.title])

    def test_anonymous_reference_is_low(self):
        refs = ["[1] Anonymous. J Adv Res 12, 1-9 (2021).",
                "[2] J. Doe. Science 380, 1-4 (2022).",
                "[3] K. Lee. Lancet 401, 88-95 (2023).",
                "[4] M. Ali. PLOS ONE 19, e0280001 (2024).",
                "[5] S. Rao. J Adv Res 12, 1-9 (2020).",
                "[6] P. Kumar. IEEE TPAMI 45, 100-112 (2023)."]
        fs = ref_forensics_run(_ref_doc(refs), CheckContext())
        hit = [f for f in fs if "no named author" in f.title]
        self.assertTrue(hit)
        self.assertEqual(hit[0].severity, Severity.LOW)

    def test_too_few_references_is_silent(self):
        refs = ["[1] A. Smith. Nature 599, 120-135 (2031).",
                "[2] J. Doe. Science 380, 1-4 (2022)."]
        self.assertEqual(ref_forensics_run(_ref_doc(refs), CheckContext()), [])


class TestTopicCoherence(unittest.TestCase):
    """Title/keywords vs body — the desk-editor's first read."""

    def _mismatched(self):
        return _doc(
            "Title: Deep Learning for Diabetic Retinopathy Screening in Clinical Practice\n\n"
            "Abstract: This paper presents a convolutional network for detecting "
            "diabetic retinopathy from fundus images in screening programs.\n\n"
            "Keywords: retinopathy, convolutional network, screening, fundus images\n\n"
            "1. Introduction\n" + _INTRO * 8 +
            "\n2. Methods\n" + _METHODS * 8 +
            "\n3. Results\n" + _RESULTS * 8 +
            "\n4. Conclusion\nFertilizer at 50 kg per hectare raised yield.")

    def test_title_body_mismatch_flags(self):
        fs = topic_run(self._mismatched(), CheckContext())
        titles = " | ".join(f.title for f in fs)
        self.assertIn("Title terms", titles)
        self.assertIn("keywords", titles.lower())

    def test_coherent_paper_is_silent(self):
        text = ("Title: Fertilizer Rate Effects on Crop Yield and Soil Moisture\n\n"
                "Abstract: Plots received 0, 50 and 100 kg per hectare; yield rose "
                "8 percent at 50 kg without extra nitrogen leaching.\n\n"
                "Keywords: fertilizer, yield, soil moisture, nitrogen leaching\n\n"
                "1. Introduction\n" + _INTRO * 8 +
                "\n2. Methods\n" + _METHODS * 8 +
                "\n3. Results\n" + _RESULTS * 8 +
                "\n4. Conclusion\nFertilizer at 50 kg per hectare raised yield.")
        self.assertEqual(topic_run(_doc(text), CheckContext()), [])

    def test_title_label_prefix_not_counted_as_a_term(self):
        """The literal word 'Title:' must not be reported as an unsupported term."""
        text = ("Title: Fertilizer Rate Effects on Crop Yield and Soil Moisture\n\n"
                "1. Introduction\n" + _INTRO * 8 +
                "\n2. Methods\n" + _METHODS * 8 +
                "\n3. Results\n" + _RESULTS * 8)
        for f in topic_run(_doc(text), CheckContext()):
            self.assertNotIn("title", f.evidence.split(":")[-1].split(",")[0].strip().lower())

    def test_short_document_is_silent(self):
        text = "Title: A Short Note\n\n1. Introduction\nToo short to judge. " * 3
        self.assertEqual(topic_run(_doc(text), CheckContext()), [])


class TestRationale(unittest.TestCase):
    """Weak rationale: top-3 post-review rejection reason (Menon 2020)."""

    def test_background_only_introduction_flags(self):
        text = ("1. Introduction\n" + _INTRO * 8 +
                "\n2. Methods\n" + _METHODS * 8 +
                "\n3. Results\n" + _RESULTS * 8 +
                "\n4. Conclusion\nFertilizer raised yield.")
        fs = rationale_run(_doc(text), CheckContext())
        self.assertTrue(fs, "an introduction with no gap/question/motivation must flag")
        self.assertEqual(fs[0].severity, Severity.MEDIUM)
        self.assertEqual(fs[0].category, "Rationale")

    def test_gap_question_motivation_is_silent(self):
        text = ("1. Introduction\nFertilizer responses are well studied in isolation. "
                "However, little is known about how leaching interacts with moisture. "
                "We ask: does moisture mediate the nitrogen loss? This matters because "
                "fertilizer runoff affects drinking water. " + _INTRO * 6 +
                "\n2. Methods\n" + _METHODS * 8 +
                "\n3. Results\n" + _RESULTS * 8 +
                "\n4. Conclusion\nMoisture mediated the loss.")
        self.assertEqual(rationale_run(_doc(text), CheckContext()), [])

    def test_missing_gap_alone_flags(self):
        text = ("1. Introduction\nWe present an analysis of nitrogen loss. "
                "The objective of this study is to quantify leaching. " + _INTRO * 8 +
                "\n2. Methods\n" + _METHODS * 8 +
                "\n3. Results\n" + _RESULTS * 8)
        fs = rationale_run(_doc(text), CheckContext())
        titles = " | ".join(f.title for f in fs)
        self.assertIn("No explicit research gap", titles)

    def test_no_introduction_is_silent(self):
        """Missing sections belong to structure/submission, not this engine."""
        text = ("Some text here that is long enough to pass the word guard. " * 60)
        self.assertEqual(rationale_run(_doc(text), CheckContext()), [])


class TestScopeMatchDefaultVenue(unittest.TestCase):
    """Scope is the top desk-reject reason; the default run must not be silent."""

    def test_generic_venue_no_longer_silent(self):
        d = Document(path="t.txt", name="t.txt", file_type="txt",
                     text="quantum entanglement study of superconductors " * 50)
        fs = scope_run(d, CheckContext(venue=describe("generic")))
        self.assertTrue(fs, "the default venue must report that scope was not checked")
        self.assertEqual(fs[0].severity, Severity.INFO)
        self.assertIn("venue", fs[0].title.lower())

    def test_info_does_not_affect_score(self):
        from papercheck.risk import Severity as S
        self.assertEqual(S.INFO.weight, 0.0,
                         "an unmeasured check must not move the readiness score")

    def test_named_venue_still_checks_scope(self):
        d = Document(path="t.txt", name="t.txt", file_type="txt",
                     text="quantum chromodynamics lattice simulations " * 50)
        ctx = CheckContext(venue=describe("ugc_care"), rules=get_rules("ugc_care"))
        fs = scope_run(d, ctx)
        self.assertTrue([f for f in fs if f.severity in (Severity.MEDIUM, Severity.LOW)])

    def test_registry_includes_new_engines(self):
        names = {fn.__module__.rsplit(".", 1)[-1] for fn in ALL_ENGINES}
        for eng in ("ref_forensics", "topic_coherence", "rationale"):
            self.assertIn(eng, names, eng + " must be registered")


if __name__ == "__main__":
    unittest.main()

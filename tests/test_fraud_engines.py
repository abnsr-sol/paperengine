"""Tests for the fraud/failure-pattern engines: citation_cartel, paper_mill, retracted_refs, predatory_journal."""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from papercheck.ingestion import Document
from papercheck.venues import get_rules
from papercheck.checks import CheckContext
from papercheck.checks.citation_cartel import run as cartel_run
from papercheck.checks.paper_mill import run as mill_run
from papercheck.checks.retracted_refs import run as retracted_run


def _doc(text, paras=None, refs=None):
    return Document(path="t.txt", name="t.txt", file_type="txt",
                    text=text, paragraphs=paras or [text], references=refs or [])


class TestCitationCartel(unittest.TestCase):
    def test_excessive_self_citation_flags(self):
        text = "We propose a framework for detection. " * 20
        refs = ["Smith, J. A framework for detection.", "Smith, J. Another self cite.",
                "Smith, J. Third self cite.", "Smith, J. Fourth self cite.",
                "Jones, B. Other work.", "Lee, C. Independent work.", "Patel, D. Unrelated."]
        paras = ["Title", "Alice Smith, Bob Jones, Carol Lee", "alice@univ.edu"]
        doc = _doc(text, paras, refs)
        fs = cartel_run(doc, CheckContext(rules=get_rules("generic")))
        self.assertTrue(any("self-citation" in f.title.lower() for f in fs))

    # --- coercive-citation / venue-stacking check (target-venue reference share) ---

    def _venue_doc(self, refs):
        return _doc("A study of venue citation patterns. " * 30, refs=refs)

    def test_venue_stacking_flags_high(self):
        refs = ["Doe J. IEEE Access transactions on computing, 2020."] * 6 + \
               ["Smith A. Journal of unrelated stuff, 2021."] * 9
        fs = cartel_run(self._venue_doc(refs),
                        CheckContext(venue="ieee_access", rules=get_rules("ieee_access")))
        hits = [f for f in fs if "target venue" in f.title.lower()]
        self.assertTrue(hits)
        self.assertEqual(hits[0].severity.value, "High")
        self.assertIn("6/15", hits[0].title)

    def test_venue_stacking_moderate_flags_medium(self):
        refs = ["Doe J. IEEE Access, 2020."] * 3 + \
               ["Smith A. Journal of unrelated stuff, 2021."] * 12
        fs = cartel_run(self._venue_doc(refs),
                        CheckContext(venue="ieee_access", rules=get_rules("ieee_access")))
        hits = [f for f in fs if "target venue" in f.title.lower()]
        self.assertTrue(hits)
        self.assertEqual(hits[0].severity.value, "Medium")

    def test_venue_stacking_no_false_positive_on_substring(self):
        # "acm" inside "Macmillan" must NOT count as an ACM citation (word boundary).
        refs = ["J. Author, On Macmillan publishing and computing, 2020."] * 5 + \
               ["B. Other, Independent work, 2021."] * 10
        fs = cartel_run(self._venue_doc(refs),
                        CheckContext(venue="acm", rules=get_rules("acm")))
        self.assertFalse(any("target venue" in f.title.lower() for f in fs))

    def test_venue_stacking_balanced_list_no_flag(self):
        refs = ["Doe J. IEEE Access, 2020."] * 2 + \
               ["Smith A. IEEE Transactions on Knowledge Engineering, 2021."] + \
               ["Lee C. Nature, 2021."] * 6 + ["Kim D. Science, 2021."] * 6
        fs = cartel_run(self._venue_doc(refs),
                        CheckContext(venue="ieee_access", rules=get_rules("ieee_access")))
        self.assertFalse(any("target venue" in f.title.lower() for f in fs))

    def test_venue_stacking_skipped_for_generic_venue(self):
        refs = ["J. Author, On ACM transactions, 2020."] * 5 + \
               ["B. Other, Independent work, 2021."] * 10
        fs = cartel_run(self._venue_doc(refs),
                        CheckContext(venue="generic", rules=get_rules("generic")))
        self.assertFalse(any("target venue" in f.title.lower() for f in fs))

    def test_venue_stacking_defaults_no_crash(self):
        refs = ["Doe J. IEEE Access, 2020."] * 6 + ["Smith A. Other, 2021."] * 9
        fs = cartel_run(self._venue_doc(refs), CheckContext())
        self.assertIsInstance(fs, list)


class TestPaperMill(unittest.TestCase):
    def test_glued_email_flags(self):
        text = "A study of outcomes. rushikesh@gmail.comBenduri Akshaya and akshaya@yahoo.comRudrarapu Rao. " * 6
        doc = _doc(text)
        fs = mill_run(doc, CheckContext(rules=get_rules("generic")))
        self.assertTrue(any("glued" in f.title.lower() for f in fs))

    def test_free_mail_hospital_rule(self):
        text = "Department of Cardiology, City Hospital. Corresponding author: j.doe@gmail.com. " * 8
        paras = [text]
        doc = _doc(text, paras)
        fs = mill_run(doc, CheckContext(rules=get_rules("generic")))
        self.assertTrue(any("free-mail" in f.title.lower() for f in fs))


class TestRetractedRefs(unittest.TestCase):
    def test_known_retraction_flags(self):
        text = "Vaccine safety was reviewed. " * 10
        refs = ["Wakefield AJ. MMR vaccine and autism. Lancet 1998;351:637.",
                "Mehra MR. Hydroxychloroquine in COVID-19. Lancet 2020."]
        doc = _doc(text, refs=refs)
        fs = retracted_run(doc, CheckContext(rules=get_rules("generic")))
        self.assertTrue(any(f.severity.value == "Critical" for f in fs))

    def test_clean_refs_no_flag(self):
        text = "A normal methods section. " * 10
        refs = ["Deng J. ImageNet classification. CVPR 2009.",
                "Vaswani A. Attention is all you need. NeurIPS 2017."]
        doc = _doc(text, refs=refs)
        fs = retracted_run(doc, CheckContext(rules=get_rules("generic")))
        self.assertFalse(any(f.severity.value == "Critical" for f in fs))


if __name__ == "__main__":
    unittest.main()

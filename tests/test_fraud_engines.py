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

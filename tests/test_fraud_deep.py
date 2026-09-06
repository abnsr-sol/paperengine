"""Tests for the latest engines: crossref_verify (offline), author_network, reviewer_fraud, image_manipulation (guards)."""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from papercheck.ingestion import Document
from papercheck.venues import get_rules
from papercheck.checks import CheckContext
from papercheck.checks.crossref_verify import run as crossref_run
from papercheck.checks.author_network import run as author_run
from papercheck.checks.reviewer_fraud import run as reviewer_run
from papercheck.checks.image_manipulation import run as image_run


class TestCrossrefOffline(unittest.TestCase):
    def test_offline_returns_nothing(self):
        doc = Document(path="t.docx", name="t.docx", file_type="docx",
                       text="text", paragraphs=["t"], references=["Some, A. Paper. 2020."])
        fs = crossref_run(doc, CheckContext(rules=get_rules("generic"), online=False))
        self.assertEqual(fs, [])


class TestAuthorNetwork(unittest.TestCase):
    def test_duplicate_identity_flags(self):
        base = Document(path="b.txt", name="b.txt", file_type="txt",
                        text="A study of detection methods. " * 20,
                        paragraphs=["Alice Smith, Bob Jones", "alice@univ.edu"])
        mine = Document(path="m.txt", name="m.txt", file_type="txt",
                        text="A study of detection methods and new results. " * 20,
                        paragraphs=["Alice Jones, Bob Jones", "alice@univ.edu"])
        ctx = CheckContext(rules=get_rules("generic"), corpus=[base])
        fs = author_run(mine, ctx)
        self.assertTrue(any("Duplicate author identity" in f.title for f in fs))

    def test_no_corpus_no_flags(self):
        doc = Document(path="m.txt", name="m.txt", file_type="txt",
                       text="A study. " * 20, paragraphs=["Alice Smith", "a@univ.edu"])
        fs = author_run(doc, CheckContext(rules=get_rules("generic"), corpus=[]))
        self.assertEqual(fs, [])


class TestReviewerFraud(unittest.TestCase):
    def test_self_review_email_flags(self):
        text = ("Suggested reviewers:\nProf. X at x@univ.edu, Prof. Y at y@univ.edu, "
                "Dr. Z at alice@gmail.com\nCorresponding author: alice@gmail.com") * 3
        doc = Document(path="r.txt", name="r.txt", file_type="txt",
                       text=text, paragraphs=[text])
        fs = reviewer_run(doc, CheckContext(rules=get_rules("generic")))
        titles = " | ".join(f.title for f in fs)
        self.assertIn("shares the authors' email", titles)

    def test_no_reviewer_block_no_flags(self):
        text = "A normal manuscript about classification. " * 6
        doc = Document(path="r.txt", name="r.txt", file_type="txt", text=text, paragraphs=[text])
        fs = reviewer_run(doc, CheckContext(rules=get_rules("generic")))
        self.assertEqual(fs, [])


class TestImageManipulation(unittest.TestCase):
    def test_txt_file_skipped(self):
        doc = Document(path="t.txt", name="t.txt", file_type="txt",
                       text="text", paragraphs=["text"])
        fs = image_run(doc, CheckContext(rules=get_rules("generic")))
        self.assertEqual(fs, [])


if __name__ == "__main__":
    unittest.main()

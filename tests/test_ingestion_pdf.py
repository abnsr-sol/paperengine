"""Layout-aware PDF extraction tests.

These build real two-column / single-column PDFs with fpdf (available in the
dev environment) and assert the *reading order* properties that every
downstream engine depends on: columns not interleaved, titles preserved,
running heads removed, ligatures and hyphenation normalized.
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

try:
    from fpdf import FPDF
except ImportError:  # pragma: no cover - dev environment extra
    FPDF = None

from papercheck.ingestion import _load_pdf, _normalize_pdf_text  # noqa: E402


def _two_column_pdf():
    pdf = FPDF(format="A4")
    pdf.set_margins(20, 20, 20)
    pdf.add_page()
    pdf.set_font("helvetica", "", 14)
    pdf.set_xy(20, 25)
    pdf.cell(0, 8, "Title Spanning Both Columns")
    pdf.set_font("helvetica", "", 10)
    for i in range(1, 8):
        pdf.set_xy(20, 45 + i * 8)
        pdf.cell(0, 8, f"LEFT sentence {i} about methods here.")
    for i in range(1, 8):
        pdf.set_xy(320, 45 + i * 8)
        pdf.cell(0, 8, f"RIGHT result {i} with numbers 0.05.")
    fd, path = tempfile.mkstemp(suffix=".pdf")
    os.close(fd)
    pdf.output(path)
    return path


def _single_column_pdf(n_pages=3, running_head="IEEE TRANSACTIONS ON TESTING, VOL. 9"):
    pdf = FPDF(format="A4")
    for p in range(n_pages):
        pdf.add_page()
        pdf.set_font("helvetica", "", 8)
        pdf.set_xy(20, 15)
        pdf.cell(0, 6, running_head)
        pdf.set_font("helvetica", "", 11)
        for i in range(20):
            pdf.set_xy(20, 30 + i * 9)
            pdf.cell(0, 9, f"Page {p} line {i} of the single column body text.")
    fd, path = tempfile.mkstemp(suffix=".pdf")
    os.close(fd)
    pdf.output(path)
    return path


@unittest.skipUnless(FPDF is not None, "fpdf not installed")
class TestTwoColumnExtraction(unittest.TestCase):
    def test_columns_not_interleaved(self):
        path = _two_column_pdf()
        try:
            doc = _load_pdf(path)
            lines = doc.text.splitlines()
            left = [l for l in lines if l.startswith("LEFT")]
            right = [l for l in lines if l.startswith("RIGHT")]
            self.assertEqual(len(left), 7)
            self.assertEqual(len(right), 7)
            li = next(i for i, l in enumerate(lines) if l.startswith("LEFT"))
            ri = next(i for i, l in enumerate(lines) if l.startswith("RIGHT"))
            self.assertLess(li, ri, "left column must be emitted before right column")
            # no line mixes LEFT and RIGHT content (the naive-extractor failure)
            for l in lines:
                self.assertFalse(
                    l.startswith("LEFT") and "RIGHT" in l,
                    f"column interleave detected: {l!r}",
                )
        finally:
            os.unlink(path)

    def test_title_preserved_and_first(self):
        path = _two_column_pdf()
        try:
            doc = _load_pdf(path)
            lines = doc.text.splitlines()
            self.assertIn("Title Spanning Both Columns", doc.text)
            self.assertTrue(
                lines[0].startswith("Title"),
                f"title must be first line, got {lines[0]!r}",
            )
        finally:
            os.unlink(path)

    def test_extraction_note_records_layout(self):
        path = _two_column_pdf()
        try:
            doc = _load_pdf(path)
            self.assertTrue(
                any("Two-column" in n for n in doc.extraction_notes),
                doc.extraction_notes,
            )
        finally:
            os.unlink(path)


@unittest.skipUnless(FPDF is not None, "fpdf not installed")
class TestRunningHeadStripping(unittest.TestCase):
    def test_repeated_head_removed_body_kept(self):
        path = _single_column_pdf()
        try:
            doc = _load_pdf(path)
            self.assertNotIn("IEEE TRANSACTIONS ON TESTING", doc.text)
            self.assertIn("Page 0 line 0", doc.text)
            self.assertIn("Page 2 line 19", doc.text)
        finally:
            os.unlink(path)

    def test_single_page_never_stripped(self):
        # A one-page paper keeps every line — a repeated-line cut could eat a
        # real title; short docs are protected by the min_pages rule.
        path = _single_column_pdf(n_pages=1, running_head="SINGLE PAGE UNIQUE HEADER")
        try:
            doc = _load_pdf(path)
            self.assertIn("SINGLE PAGE UNIQUE HEADER", doc.text)
        finally:
            os.unlink(path)


class TestTextNormalization(unittest.TestCase):
    def test_ligatures(self):
        self.assertEqual(_normalize_pdf_text("qualiﬁed eﬃcient"), "qualified efficient")

    def test_zero_width_and_soft_hyphens_removed(self):
        self.assertEqual(_normalize_pdf_text("net\u200bwork re\u00adnewal"), "network renewal")

    def test_de_hyphenation(self):
        self.assertEqual(_normalize_pdf_text("sig-\nnificant"), "significant")

    def test_replacement_char_removed(self):
        self.assertEqual(_normalize_pdf_text("da\u00a0ta\ufffd"), "da ta")


if __name__ == "__main__":
    unittest.main()

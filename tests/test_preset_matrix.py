"""Preset-matrix regression tests.

Guards against the v1.8.0 GUI crash class: a venue preset or a bad Finding
type that aborts the whole report. Every venue preset must produce a valid
HTML report with a real readiness score (international matrix), the national
standard must stay coherent, and the DOCX parse path gets a spot-check.
Also locks in the Finding type-coercion armor and per-engine isolation.
"""
import io
import os
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from papercheck.risk import Finding, RiskReport, Severity  # noqa: E402
from papercheck.venues import PRESETS  # noqa: E402

DOC = (
    "# Title of the Study\n\n## Abstract\nThis study examines method X on outcome Y "
    "with n=150 participants. Results were significant (t(28) = 2.45, p = .021). "
    "The mean was 3.5 (SD = 1.2). Keywords: machine learning, deep learning.\n\n"
    "## 1. Introduction\nMachine learning has transformed domains. Prior work [1] showed gains. "
    "We refer to Figure 3 and Table 2. Random forest models were used.\n\n"
    "## 2. Methods\nWe trained a 70B parameter model on 4 GPUs with AdamW for 100 epochs. "
    "Participants completed a 7-point Likert scale (M = 4.2, SD = 0.9, N = 30). "
    "Data available on request. Ethics approval was obtained.\n\n"
    "## 3. Results\nAccuracy was 97%. p = 0.048, p = 0.049 without correction. "
    "See https://github.com/user/repo/tree/main for code.\n\n"
    "## 4. Discussion\nThis suggests an association between X and Y.\n\n"
    "## References\n"
    "[1] Smith, J. (2020). On learning. Journal of Things. doi: 10.1000/fake-doi-xx\n"
    "[2] Doe, A. (2019). More things. doi: 10.1000/fake-doi-yy\n"
    "[3] Roe, B. (2018). Even more. doi: 10.1000/fake-doi-zz\n"
    "[4] Coe, C. (2017). Things again. doi: 10.1000/fake-doi-ww\n"
    "[5] Woe, D. (2016). Final things. doi: 10.1000/fake-doi-vv\n"
    "[6] Nee, E. (2015). Sixth thing. doi: 10.1000/fake-doi-uu\n"
    "[7] Pee, F. (2014). Seventh thing. doi: 10.1000/fake-doi-tt\n"
    "[8] Gee, G. (2013). Eighth thing. doi: 10.1000/fake-doi-ss\n"
) + ("Additional context sentence for padding length. " * 60)


def _docx_bytes(text: str) -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as z:
        z.writestr(
            "[Content_Types].xml",
            '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="xml" ContentType="application/xml"/></Types>')
        import html as _h
        body = "".join(
            "<w:p><w:r><w:t xml:space=\"preserve\">%s</w:t></w:r></w:p>" % _h.escape(line)
            for line in text.splitlines() if line.strip())
        z.writestr(
            "word/document.xml",
            '<?xml version="1.0"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            '<w:body>%s</w:body></w:document>' % body)
    return out.getvalue()


class TestFindingCoercion(unittest.TestCase):
    """The 'bad operand type for unary -: str' crash class."""

    def test_string_confidence_never_crashes_sort(self):
        f = Finding("T", "high", "t", "d", "e", "a", "0.9")
        self.assertIsInstance(f.confidence, float)
        self.assertEqual(f.confidence, 0.9)

    def test_transposed_args_still_sort_and_score(self):
        r = RiskReport("x", "y", findings=[
            Finding("T", "Medium", "t", "d", "e", "a", "0.5"),
            Finding("T", "Critical", "t", "d", "e", "a", 0.8),
            Finding("T", None, "t", "d", "e", "a", None),
        ])
        order = [f.severity.name for f in r.by_severity()]
        self.assertEqual(order, ["CRITICAL", "MEDIUM", "INFO"])
        self.assertTrue(0 <= r.readiness_score <= 100)

    def test_string_severity_coerces(self):
        f = Finding("T", "critical", "t", "d", "e", "a", 0.9)
        self.assertEqual(f.severity, Severity.CRITICAL)

    def test_non_string_text_fields_coerce(self):
        f = Finding("T", "info", "t", "d", "e", 12345, 0.7)
        self.assertEqual(f.action, "12345")  # 6th positional slot is action
        self.assertIsInstance(f.action, str)

    def test_none_fields_become_empty(self):
        f = Finding("T", None, "t", None, None, None, None)
        self.assertEqual(f.detail, "")
        self.assertEqual(f.evidence, "")
        self.assertEqual(f.action, "")
        self.assertEqual(f.confidence, 0.5)

    def test_confidence_clamps(self):
        self.assertEqual(Finding("T", "low", "t", "d", "e", "a", 7.5).confidence, 1.0)
        self.assertEqual(Finding("T", "low", "t", "d", "e", "a", -2).confidence, 0.0)


class TestEngineIsolation(unittest.TestCase):
    """One raising engine must never blank a report."""

    def test_run_all_engines_isolates_failures(self):
        from papercheck.checks import run_all_engines, CheckContext
        from papercheck.ingestion import Document
        from unittest import mock

        doc = Document(path="t.txt", name="t", text="hello world " * 50,
                       file_type=".txt")
        ctx = CheckContext()

        def exploding(doc, ctx):
            raise RuntimeError("boom")

        with mock.patch("papercheck.checks.ALL_ENGINES", [exploding]):
            findings, errors = run_all_engines(doc, ctx)
        self.assertEqual(len(errors), 1)
        self.assertIn("boom", errors[0])
        self.assertEqual(len(findings), 1)  # the LOW-severity engine-error note
        self.assertEqual(findings[0].severity, Severity.LOW)


class TestPresetMatrix(unittest.TestCase):
    """Every venue preset must produce a valid report end to end."""

    def _check_one(self, data: bytes, filename: str, venue: str, standard: str) -> str:
        from papercheck.webui import _run_check
        html = _run_check(filename, data, standard, venue)
        self.assertIsInstance(html, str)
        self.assertNotIn("Checking failed", html)
        self.assertIn("readiness", html.lower())
        return html

    def test_all_venues_render_international(self):
        data = DOC.encode("utf-8")
        for venue in sorted(PRESETS):
            with self.subTest(venue=venue):
                self._check_one(data, "paper.txt", venue, "international")

    def test_national_standard_coherence(self):
        data = DOC.encode("utf-8")
        for venue in ("ugc_care", "ugc_phd_thesis", "scopus_indian", "naac_journal"):
            with self.subTest(venue=venue):
                html = self._check_one(data, "paper.txt", venue, "national")
                self.assertIn("National (Indian)", html)

    def test_docx_parse_path_spot_check(self):
        data = _docx_bytes(DOC)
        for venue in ("generic", "ieee_conference", "nature", "ugc_care"):
            with self.subTest(venue=venue):
                self._check_one(data, "paper.docx", venue, "international")

    def test_report_score_intact(self):
        from papercheck.__main__ import build_report
        fd, path = tempfile.mkstemp(suffix=".txt")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(DOC)
            report = build_report(path, venue="ieee_conference", venue_json=None,
                                  corpus=None, online=False, mailto="", max_online=0)
            self.assertTrue(0 <= report.readiness_score <= 100)
            self.assertGreater(len(report.findings), 3)
        finally:
            os.unlink(path)


if __name__ == "__main__":
    unittest.main()

"""Tests for supplementary, llm_artifacts, data_license engines."""
import unittest
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from papercheck.ingestion import Document
from papercheck.checks import supplementary, llm_artifacts, data_license


def _doc(text, refs=None):
    return Document(path='x', name='x', file_type='txt', text=text, references=refs or [])


class TestSupplementary(unittest.TestCase):
    def test_missing_supp_section(self):
        out = supplementary.run(_doc('Plain results only.'), None)
        self.assertTrue(any('No supplementary material section' in f.title for f in out))

    def test_numbered_supp_ok(self):
        out = supplementary.run(_doc('Supplementary Figure 1 shows details.'), None)
        self.assertFalse(any('not numbered' in f.title for f in out))

    def test_data_not_shown(self):
        out = supplementary.run(_doc('The data are not shown here.'), None)
        self.assertTrue(any("not shown" in f.title for f in out))


class TestLLMArtifacts(unittest.TestCase):
    def test_template_phrasing(self):
        out = llm_artifacts.run(_doc('It is important to note that we delve into this.'), None)
        self.assertTrue(any('template phrasing' in f.title for f in out))

    def test_tortured_phrase(self):
        out = llm_artifacts.run(_doc('We use profound learning for vision.'), None)
        self.assertTrue(any('ortured' in f.title for f in out))

    def test_placeholder(self):
        out = llm_artifacts.run(_doc('Results are TBD.'), None)
        self.assertTrue(any('Placeholder' in f.title for f in out))

    def test_fake_ref_signature(self):
        out = llm_artifacts.run(_doc('See doi: N/A for details.', ['ref']), None)
        self.assertTrue(any('Hallucinated-reference' in f.title for f in out))


class TestDataLicense(unittest.TestCase):
    def test_no_statement(self):
        out = data_license.run(_doc('We analyze survey data.'), None)
        self.assertTrue(any('No data availability' in f.title for f in out))

    def test_license_missing_with_repo(self):
        out = data_license.run(_doc('Our dataset is on Zenodo.'), None)
        self.assertTrue(any('without an open license' in f.title for f in out))

    def test_proprietary_format(self):
        out = data_license.run(_doc('Data in proprietary format.'), None)
        self.assertTrue(any('Proprietary' in f.title for f in out))


if __name__ == '__main__':
    unittest.main()

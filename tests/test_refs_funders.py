"""Tests for reference_completeness and funder_compliance engines."""
import unittest
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from papercheck.ingestion import Document
from papercheck.checks import reference_completeness, funder_compliance


def _doc(text, refs=None):
    return Document(path='x', name='x', file_type='txt', text=text, references=refs or [])


class TestReferenceCompleteness(unittest.TestCase):
    def test_missing_years(self):
        refs = ['Smith, A. Uncertainty analysis, no year listed', 'Jones, B. Method design, yearless entry',
                'Lee, C. Results section, nothing here', 'Wu, D. Discussion notes only',
                'Patel, E. More yearless content', 'Kim, F. Another one without year']
        out = reference_completeness.run(_doc('Body.', refs), None)
        self.assertTrue(any('missing a year' in f.title for f in out))

    def test_secondary_citations(self):
        refs = ['A 2020 journal paper, 12(3), 45-52'] * 8
        out = reference_completeness.run(_doc('As cited in Brown (2019) and as cited in Davis (2020).', refs), None)
        self.assertTrue(any('Secondary-source' in f.title for f in out))

    def test_complete_refs_clean(self):
        refs = ['Smith, A. (2020). Title. Journal, 12(3), 45-52.', 'Jones, B. (2021). Title. Journal, 5(2), 100-110.',
                'Lee, C. (2019). Title. Journal, 8(1), 1-9.', 'Wu, D. (2022). Title. Journal, 3(4), 7-14.',
                'Patel, E. (2020). Title. Journal, 15(2), 20-30.', 'Kim, F. (2021). Title. Journal, 9(3), 55-60.']
        out = reference_completeness.run(_doc('Body.', refs), None)
        self.assertEqual(out, [])


class TestFunderCompliance(unittest.TestCase):
    def test_nih_no_pmc(self):
        out = funder_compliance.run(_doc('This work was funded by NIH grant support. Our dataset is available.'), None)
        self.assertTrue(any('PMC' in f.title for f in out))
        self.assertTrue(any('grant numbers' in f.title for f in out))

    def test_plan_s_no_oa(self):
        out = funder_compliance.run(_doc('Funded by Wellcome Trust. Dataset available.'), None)
        self.assertTrue(any('open-access' in f.title for f in out))

    def test_compliant_clean(self):
        out = funder_compliance.run(_doc('Funded by Wellcome Trust grant WT12345 (grant number WT12345). '
                                         'Published open access under CC BY; deposited in PMC. Data available. Data management plan filed.'), None)
        self.assertFalse(any('open-access' in f.title for f in out))


if __name__ == '__main__':
    unittest.main()
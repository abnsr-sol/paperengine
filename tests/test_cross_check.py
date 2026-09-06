"""Tests for cross_check engine (inconsistent n, duplicate data, numeric contradictions)."""
import unittest
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from papercheck.ingestion import Document
from papercheck.checks import cross_check


def _doc(text, figs=0, tables=0):
    return Document(path='x', name='x', file_type='txt', text=text,
                    figures=figs, tables=tables, references=[])


class TestCrossCheck(unittest.TestCase):
    def test_inconsistent_n_flagged(self):
        d = _doc('Group A had n = 100, group B n = 101, group C n = 102 participants.')
        out = cross_check.run(d, None)
        self.assertTrue(any('inconsistent sample sizes' in f.title for f in out))

    def test_per_group_framing_clean(self):
        d = _doc('n = 100 per group, with n = 200 total across sites and n = 150 in arm B respectively.')
        out = cross_check.run(d, None)
        self.assertFalse(any('inconsistent sample sizes' in f.title for f in out))

    def test_duplicate_fig_table_data(self):
        d = _doc('Figure 3 shows 45.2 accuracy. Table 3 lists 45.2 accuracy.', figs=3, tables=2)
        out = cross_check.run(d, None)
        self.assertTrue(any('duplicate data' in f.title for f in out))

    def test_numeric_contradiction(self):
        d = _doc('Accuracy increased to 10% compared to 30% at baseline in our tests.')
        out = cross_check.run(d, None)
        self.assertTrue(any('numeric-word contradictions' in f.title for f in out))

    def test_normal_comparison_clean(self):
        d = _doc('Accuracy improved to 45% compared to 10% at baseline.')
        out = cross_check.run(d, None)
        self.assertFalse(any('contradictions' in f.title for f in out))


if __name__ == '__main__':
    unittest.main()
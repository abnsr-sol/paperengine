"""Tests for domain_checklists2 (MOOSE/TREND/STREGA/CHEERS/PRISMA-ScR)."""
import unittest
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from papercheck.ingestion import Document
from papercheck.checks import domain_checklists2


def _doc(text):
    return Document(path='x', name='x', file_type='txt', text=text, references=[])


class TestDomainChecklists2(unittest.TestCase):
    def test_moose_missing_items(self):
        out = domain_checklists2.run(_doc('We did a meta-analysis of observational cohort studies with pooled odds ratio.'), None)
        self.assertTrue(any('MOOSE' in f.action for f in out))

    def test_moose_complete_clean(self):
        out = domain_checklists2.run(_doc('Meta-analysis of observational studies: I-squared assessed heterogeneity, '
                                          'funnel plot checked publication bias, random-effects model used, '
                                          'subgroup and sensitivity analyses performed.'), None)
        self.assertFalse(any('meta-analysis' in f.title.lower() for f in out))

    def test_cheers_missing(self):
        out = domain_checklists2.run(_doc('A cost-effectiveness analysis with QALYs was performed.'), None)
        self.assertTrue(any('Discounting' in f.title for f in out))

    def test_strega_missing(self):
        out = domain_checklists2.run(_doc('We performed a genome-wide association study of SNPs.'), None)
        self.assertTrue(any('Hardy-Weinberg' in f.title for f in out))

    def test_irrelevant_study_skipped(self):
        out = domain_checklists2.run(_doc('We benchmark sorting algorithms on synthetic arrays.'), None)
        self.assertEqual(out, [])


if __name__ == '__main__':
    unittest.main()
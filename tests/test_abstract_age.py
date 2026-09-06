"""Tests for abstract_quality and citation_age engines."""
import unittest
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from papercheck.ingestion import Document
from papercheck.checks import abstract_quality, citation_age


def _doc(text, refs=None):
    return Document(path='x', name='x', file_type='txt', text=text, references=refs or [])


class _Ctx:
    def __init__(self, rules=None):
        self.rules = rules or {}


class TestAbstractQuality(unittest.TestCase):
    def test_over_limit(self):
        ctx = _Ctx({'abstract_max_words': 200})
        out = abstract_quality.run(_doc('Abstract\n' + 'word ' * 250), ctx)
        self.assertTrue(any('over venue limit' in f.title for f in out))

    def test_generic_keywords(self):
        out = abstract_quality.run(_doc('Abstract\nshort.\nKeywords: analysis, study, method'), _Ctx())
        self.assertTrue(any('Generic keywords' in f.title for f in out))

    def test_too_few_keywords(self):
        out = abstract_quality.run(_doc('Abstract\nshort.\nKeywords: analysis'), _Ctx())
        self.assertTrue(any('Too few keywords' in f.title for f in out))

    def test_clinical_structured(self):
        out = abstract_quality.run(_doc('Abstract\nWe studied 100 patients.\nClinical trial results.'),
                                   _Ctx())
        self.assertTrue(any('structured format' in f.title for f in out))


class TestCitationAge(unittest.TestCase):
    def test_stale_refs(self):
        out = citation_age.run(_doc('body', ['Smith 1985, vol 3', 'Jones 1990', 'Lee 1978', 'Kumar 1982']), None)
        self.assertTrue(any('stale' in f.title for f in out))

    def test_recent_refs_clean(self):
        out = citation_age.run(_doc('body', ['A 2024', 'B 2025', 'C 2023', 'D 2024']), None)
        self.assertFalse(any('stale' in f.title for f in out))

    def test_no_years_no_findings(self):
        out = citation_age.run(_doc('body', ['ref one', 'ref two']), None)
        self.assertEqual(out, [])


if __name__ == '__main__':
    unittest.main()
"""Tests for sex_gender and stats_plan engines."""
import unittest
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from papercheck.ingestion import Document
from papercheck.checks import sex_gender, stats_plan


def _doc(text):
    return Document(path='x', name='x', file_type='txt', text=text, references=[])


class TestSexGender(unittest.TestCase):
    def test_no_sex_report(self):
        out = sex_gender.run(_doc('We studied 200 patients with a clinical diagnosis.'), None)
        self.assertTrue(any('Sex/gender not reported' in f.title for f in out))

    def test_sex_reported_clean(self):
        out = sex_gender.run(_doc('We studied 100 men and 100 women. Results are stratified by sex.'), None)
        self.assertFalse(any('not reported' in f.title for f in out))

    def test_non_subject_study_skipped(self):
        out = sex_gender.run(_doc('We benchmark five algorithms on standard datasets.'), None)
        self.assertEqual(out, [])


class TestStatsPlan(unittest.TestCase):
    def test_missing_data_not_described(self):
        out = stats_plan.run(_doc('We surveyed participants. Statistical analysis used t-tests.'), None)
        self.assertTrue(any('Missing-data handling' in f.title for f in out))

    def test_missing_data_described_clean(self):
        out = stats_plan.run(_doc('Missing data were handled by multiple imputation. Regression was used.'), None)
        self.assertFalse(any('Missing-data handling' in f.title for f in out))

    def test_no_stats_skipped(self):
        out = stats_plan.run(_doc('We describe the framework and its properties.'), None)
        self.assertEqual(out, [])


if __name__ == '__main__':
    unittest.main()
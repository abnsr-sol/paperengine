"""Tests for authorship and repro_env engines."""
import unittest
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from papercheck.ingestion import Document
from papercheck.checks import authorship, repro_env


def _doc(text):
    return Document(path='x', name='x', file_type='txt', text=text, references=[])


class TestAuthorship(unittest.TestCase):
    def test_no_credit_roles(self):
        out = authorship.run(_doc('This work was funded by grant ABC. The authors declare no conflict of interest.'), None)
        self.assertTrue(any('No CRediT' in f.title for f in out))
        self.assertTrue(any('role-of-funders' in f.title for f in out))

    def test_full_credit_clean(self):
        out = authorship.run(_doc('Conflicts of interest: none. Funding: XYZ (role of funding source: none). '
                                  'Author contributions: Conceptualization, A; Methodology, B; Software, A; Formal analysis, B; Supervision, C.'), None)
        self.assertFalse(any('No CRediT' in f.title for f in out))

    def test_thin_credit(self):
        out = authorship.run(_doc('Conflict of interest: none. Funding: none. Author contributions: Conceptualization, A.'), None)
        self.assertTrue(any('Thin CRediT' in f.title for f in out))


class TestReproEnv(unittest.TestCase):
    def test_ml_no_code(self):
        out = repro_env.run(_doc('We trained our model on the dataset and evaluated on the test set.'), None)
        self.assertTrue(any('code-availability' in f.title for f in out))

    def test_code_available_clean(self):
        out = repro_env.run(_doc('We trained the model. Code is publicly available at github.com/example/repo. '
                                 'Environment: Docker container with requirements.txt. We used 5-fold cross-validation split.'), None)
        self.assertFalse(any('code-availability' in f.title for f in out))
        self.assertFalse(any('computational-environment' in f.title for f in out))

    def test_trial_not_registered(self):
        out = repro_env.run(_doc('This randomized clinical trial followed a written protocol.'), None)
        self.assertTrue(any('protocol not registered' in f.title for f in out))


if __name__ == '__main__':
    unittest.main()
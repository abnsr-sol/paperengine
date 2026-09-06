"""Tests for the Retraction Watch database module and its retracted_refs integration."""
import unittest
import sys, os, tempfile, shutil
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from papercheck.ingestion import Document
from papercheck.rwdb import load_db, screen_references
from papercheck.checks import retracted_refs


class TestRwdb(unittest.TestCase):
    def test_seed_list_loads(self):
        entries = load_db(None)
        self.assertGreaterEqual(len(entries), 10)

    def test_missing_file_falls_back_to_seed(self):
        entries = load_db(os.path.join(os.devnull, 'nonexistent.json'))
        self.assertGreaterEqual(len(entries), 10)

    def test_full_db_parse(self):
        tmp = tempfile.mkdtemp()
        try:
            path = os.path.join(tmp, 'rwdb.json')
            import json
            with open(path, 'w', encoding='utf-8') as fh:
                json.dump([
                    {"title": "Wakefield MMR autism study", "year": 1998, "reason": "fraud"},
                    {"title": "Another fake covid paper", "year": 2020, "reason": "duplicate"},
                ], fh)
            entries = load_db(path)
            self.assertEqual(len(entries), 2)
            self.assertEqual(entries[0]['title'].lower(), 'wakefield mmr autism study')
        finally:
            shutil.rmtree(tmp)

    def test_screen_flags_match(self):
        refs = ['Wakefield et al. (1998) MMR vaccine study, Lancet']
        hits = screen_references(refs, load_db(None))
        self.assertEqual(len(hits), 1)
        self.assertIn('wakefield', hits[0][2])

    def test_screen_no_match(self):
        refs = ['Completely unrelated safe reference (2021), Journal of Tests']
        self.assertEqual(screen_references(refs, load_db(None)), [])


class TestRetractedRefsRwdb(unittest.TestCase):
    def test_engine_uses_rwdb(self):
        d = Document(path='x', name='x', file_type='txt', text='body',
                     references=['Wakefield et al. (1998) MMR vaccine study, Lancet'])
        out = retracted_refs.run(d, None)
        self.assertTrue(any('retracted' in f.title.lower() for f in out))

    def test_engine_clean(self):
        d = Document(path='x', name='x', file_type='txt', text='body',
                     references=['Smith et al. (2021) Safe methods paper, Journal of Science'])
        out = retracted_refs.run(d, None)
        self.assertFalse(any('matches a well-known retracted' in f.title for f in out))


if __name__ == '__main__':
    unittest.main()
"""Tests for batch folder scanning."""
import unittest
import sys, os, tempfile, shutil
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from papercheck.batch import scan_folder, write_csv, render_console_table


class TestBatch(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        with open(os.path.join(self.tmp, 'good.txt'), 'w', encoding='utf-8') as fh:
            fh.write("Abstract\nWe study clustering of graphs and networks with methods and results. " * 20)
        with open(os.path.join(self.tmp, 'empty.txt'), 'w', encoding='utf-8') as fh:
            fh.write("")
        with open(os.path.join(self.tmp, 'ignored.xyz'), 'w', encoding='utf-8') as fh:
            fh.write("not a paper")

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_scan_finds_supported_files(self):
        rows = scan_folder(self.tmp, 'ugc_care')
        names = {r['file'] for r in rows}
        self.assertIn('good.txt', names)
        self.assertNotIn('ignored.xyz', names)

    def test_scores_sorted_worst_first(self):
        rows = scan_folder(self.tmp, 'ugc_care')
        scores = [r['readiness'] for r in rows]
        self.assertEqual(scores, sorted(scores))

    def test_counts_present(self):
        rows = scan_folder(self.tmp, 'ugc_care')
        for r in rows:
            self.assertIn('readiness', r)
            self.assertIn('findings', r)
            self.assertIn('top_findings', r)

    def test_csv_written(self):
        rows = scan_folder(self.tmp, 'ugc_care')
        out = os.path.join(self.tmp, 'out.csv')
        write_csv(rows, out)
        with open(out, encoding='utf-8') as fh:
            header = fh.readline().strip()
        self.assertIn('readiness', header)

    def test_console_table(self):
        rows = scan_folder(self.tmp, 'ugc_care')
        text = render_console_table(rows)
        self.assertIn('good.txt', text)
        self.assertIn('Sorted worst-first', text)


if __name__ == '__main__':
    unittest.main()
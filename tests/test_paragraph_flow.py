"""Tests for paragraph_structure and transitions engines."""
import unittest
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from papercheck.ingestion import Document, Section
from papercheck.checks import paragraph_structure, transitions


def _doc(text, paras=None):
    return Document(path='x', name='x', file_type='txt', text=text, paragraphs=paras or [], references=[])


class TestParagraphStructure(unittest.TestCase):
    def test_long_paragraph(self):
        paras = ['The analysis proceeded with many steps and observations. ' + 'word ' * 250]
        out = paragraph_structure.run(_doc(' '.join(paras), paras), None)
        self.assertTrue(any('200 words' in f.title for f in out))

    def test_vague_openers(self):
        paras = ['It is the best approach available today for this class of problems.',
                 'They achieve superior results consistently in every benchmark.',
                 'Such methods are widely used in practice across the industry.',
                 'Methods describe the approach used in the study with adequate detail.']
        out = paragraph_structure.run(_doc(' '.join(paras), paras), None)
        self.assertTrue(any('vague references' in f.title for f in out))

    def test_short_paras_skipped(self):
        paras = ['Tiny.']
        out = paragraph_structure.run(_doc('Tiny.', paras), None)
        self.assertEqual(out, [])


class TestTransitions(unittest.TestCase):
    def test_abrupt_section_shifts(self):
        secs = [Section(heading='Introduction', level=1, body='Photosynthesis converts light energy in plants.', start_index=0),
                Section(heading='Methods', level=1, body='The compiler optimizes register allocation loops.', start_index=100),
                Section(heading='Results', level=1, body='Quantum entanglement measurements exceeded expectations.', start_index=200)]
        d = Document(path='x', name='x', file_type='txt',
                     text='Photosynthesis converts light energy. The compiler optimizes. Quantum entanglement.',
                     sections=secs, references=[])
        out = transitions.run(d, None)
        self.assertTrue(any('Abrupt topic shifts' in f.title for f in out))

    def test_connected_sections_clean(self):
        secs = [Section(heading='Introduction', level=1, body='We study graphs and network clustering methods.', start_index=0),
                Section(heading='Methods', level=1, body='Our clustering method processes graphs as follows.', start_index=100),
                Section(heading='Results', level=1, body='The clustering results on graphs show clear improvement.', start_index=200)]
        d = Document(path='x', name='x', file_type='txt',
                     text='We study graphs. Our clustering method processes graphs. The clustering results on graphs.',
                     sections=secs, references=[])
        out = transitions.run(d, None)
        self.assertFalse(any('Abrupt topic shifts' in f.title for f in out))


if __name__ == '__main__':
    unittest.main()
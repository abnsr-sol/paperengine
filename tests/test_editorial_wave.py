"""Tests for editorial_format, author_info, figure_quality, venue_extras, ai_disclosure_deep, safety_ethics."""
import unittest
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from papercheck.ingestion import Document
from papercheck.checks import editorial_format, author_info, figure_quality, venue_extras, ai_disclosure_deep, safety_ethics

BS = chr(92)


def _doc(text):
    return Document(path='x', name='x', file_type='txt', text=text, references=[])


class _Ctx:
    def __init__(self, venue='', rules=None):
        self.venue = venue
        self.rules = rules or {}


class TestEditorialFormat(unittest.TestCase):
    def test_tex_generic_class(self):
        d = Document(path='x', name='x', file_type='tex',
                     text=BS + 'documentclass{article}' + BS + 'title{T} Abstract. Introduction. Conclusion. ' + 'word ' * 600, references=[])
        out = editorial_format.run(d, None)
        self.assertTrue(any("Generic 'article' class" in f.title for f in out))
        self.assertTrue(any('line numbers' in f.title for f in out))

    def test_docx_skips_tex_checks(self):
        out = editorial_format.run(_doc('Plain text paper. Abstract. Introduction.'), None)
        self.assertFalse(any('line numbers' in f.title for f in out))


class TestAuthorInfo(unittest.TestCase):
    def test_no_affiliation(self):
        out = author_info.run(_doc('A. B. Smith, C. D. Jones\nsmith@example.com\nWe present results.'), None)
        self.assertTrue(any('No institutional affiliation' in f.title for f in out))
        self.assertTrue(any('initials only' in f.title for f in out))

    def test_affiliated_clean(self):
        out = author_info.run(_doc('John Smith and Jane Jones\nDepartment of Computer Science, Example University\nCorresponding author: smith@example.com'), None)
        self.assertFalse(any('No institutional affiliation' in f.title for f in out))


class TestFigureQuality(unittest.TestCase):
    def test_western_blot_missing_controls(self):
        out = figure_quality.run(_doc('Western blot analysis was performed.'), None)
        self.assertTrue(any('markers/controls' in f.title for f in out))

    def test_blot_with_controls_clean(self):
        out = figure_quality.run(_doc('Western blot with molecular weight markers and actin loading control. Uncropped blots in supplementary.'), None)
        self.assertFalse(any('markers/controls' in f.title for f in out))

    def test_microscopy_scale_bar(self):
        out = figure_quality.run(_doc('Confocal microscopy images of stained tissue.'), None)
        self.assertTrue(any('scale bar' in f.title for f in out))


class TestVenueExtras(unittest.TestCase):
    def test_acm_ccs(self):
        out = venue_extras.run(_doc('We present a study.'), _Ctx(venue='acm'))
        self.assertTrue(any('CCS concepts' in f.title for f in out))

    def test_elsevier_highlights(self):
        out = venue_extras.run(_doc('We present a study.'), _Ctx(venue='elsevier'))
        self.assertTrue(any('Highlights' in f.title for f in out))

    def test_ccs_present_clean(self):
        out = venue_extras.run(_doc('CCS Concepts: Security and privacy'), _Ctx(venue='acm'))
        self.assertFalse(any('CCS concepts' in f.title for f in out))


class TestAIDisclosureDeep(unittest.TestCase):
    def test_tool_named_no_disclosure(self):
        out = ai_disclosure_deep.run(_doc('We used ChatGPT for drafting.'), None)
        self.assertTrue(any('without disclosure' in f.title for f in out))

    def test_disclosed_clean(self):
        out = ai_disclosure_deep.run(_doc('We used ChatGPT; its use is disclosed here per policy: language editing only, verified by humans.'), None)
        self.assertFalse(any('named without disclosure' in f.title for f in out))

    def test_ai_image_undisclosed(self):
        out = ai_disclosure_deep.run(_doc('Figure created with Midjourney.'), None)
        self.assertTrue(any('AI-generated figures' in f.title for f in out))


class TestSafetyEthics(unittest.TestCase):
    def test_pathogen_no_bsl(self):
        out = safety_ethics.run(_doc('We cultured the virus in a randomized clinical trial of the vaccine.'), None)
        self.assertTrue(any('biosafety level' in f.title for f in out))
        self.assertTrue(any('safety-monitoring' in f.title for f in out))

    def test_bsl_stated_clean(self):
        out = safety_ethics.run(_doc('All virus work was performed at BSL-3. The trial had a DSMB and adverse events were reported.'), None)
        self.assertFalse(any('biosafety level' in f.title for f in out))


if __name__ == '__main__':
    unittest.main()
"""Smoke tests for the PaperCheck engine (stdlib unittest)."""

import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from papercheck.checks import ALL_ENGINES, CheckContext
from papercheck.ingestion import Document, Section
from papercheck.ingestion import load_document
from papercheck.metrics import (
    flesch_reading_ease,
    passive_voice_ratio,
    repeated_phrase_density,
    sentence_burstiness,
    sentences,
    type_token_ratio,
    word_count,
)
from papercheck.report import render_console, render_html, render_markdown
from papercheck.risk import Finding, RiskReport, Severity
from papercheck.venues import get_rules

SAMPLE_TXT = os.path.join(ROOT, "sample_paper.txt")
SAMPLE_DOCX = os.path.join(ROOT, "sample_paper.docx")


class TestMetrics(unittest.TestCase):
    def test_word_count(self):
        self.assertEqual(word_count("hello world, this is a test"), 6)

    def test_sentences(self):
        text = "First sentence. Second one! Is this third? Yes."
        self.assertEqual(len(sentences(text)), 4)

    def test_ttr_and_burstiness(self):
        text = ("The quick brown fox jumps over the lazy dog. "
                "The quick brown fox jumps again over the dog. "
                "Foxes jump. Dogs sleep. Brown is a color. " * 5)
        self.assertGreater(type_token_ratio(text), 0.0)
        self.assertGreaterEqual(sentence_burstiness(text), 0.0)

    def test_readability_ranges(self):
        easy = flesch_reading_ease("The cat sat on the mat. The dog ran home.")
        hard = flesch_reading_ease(
            "Notwithstanding the aforementioned methodological postulations, "
            "the operationalization of construct-validated paradigms remains exigent."
        )
        self.assertGreater(easy, hard)

    def test_passive_and_repetition(self):
        passive = "The model was trained on data. The results were recorded. The file was saved."
        self.assertGreater(passive_voice_ratio(passive), 0.1)
        repeated = "the framework achieves good performance. the framework achieves good performance. " * 3
        self.assertGreater(repeated_phrase_density(repeated), 0.0)


class TestIngestion(unittest.TestCase):
    def test_txt_ingestion(self):
        doc = load_document(SAMPLE_TXT)
        self.assertGreater(doc.word_count, 500)
        self.assertGreater(len(doc.sections), 4)
        self.assertGreater(len(doc.references), 10)
        self.assertIn("Abstract", [s.heading for s in doc.sections])

    def test_docx_ingestion(self):
        if not os.path.exists(SAMPLE_DOCX):
            self.skipTest("sample_paper.docx not generated")
        doc = load_document(SAMPLE_DOCX)
        self.assertGreater(doc.word_count, 500)
        self.assertTrue(doc.font_warnings, "mixed fonts should be detected in the sample docx")


class TestEngines(unittest.TestCase):
    def _run(self, doc):
        ctx = CheckContext(rules=get_rules("elsevier"))
        findings = []
        for engine in ALL_ENGINES:
            findings.extend(engine(doc, ctx))
        return findings

    def test_all_engines_produce_findings_on_sample(self):
        doc = load_document(SAMPLE_TXT)
        ctx = CheckContext(rules=get_rules("generic"))
        # Tight rules force compliance findings on the sample paper.
        ctx.rules.update({
            "word_limit": 1000,
            "abstract_word_limit": 100,
            "min_references": 30,
            "required_sections": ["Abstract", "Introduction", "Discussion", "Conclusion", "References"],
        })
        findings = []
        for engine in ALL_ENGINES:
            findings.extend(engine(doc, ctx))
        cats = {f.category for f in findings}
        self.assertIn("Compliance", cats)
        self.assertIn("Language", cats)
        self.assertIn("AI-risk", cats)
        self.assertGreater(len(findings), 8)

    def test_corpus_overlap_detects_duplicate(self):
        from papercheck.ingestion import Document

        base = load_document(SAMPLE_TXT)
        dup = Document(
            path="dup.txt", name="dup.txt", file_type="txt",
            text=base.text[:4000], paragraphs=base.paragraphs[:20],
        )
        ctx = CheckContext(rules=get_rules("generic"), corpus=[base])
        from papercheck.checks.integrity import run as integrity_run

        findings = integrity_run(dup, ctx)
        self.assertTrue(any(f.severity == Severity.HIGH or f.severity == Severity.CRITICAL for f in findings))

    def test_venue_rules_override(self):
        rules = get_rules("ieee_conference")
        self.assertEqual(rules["page_limit"], 8)
        rules2 = get_rules("mdpi")
        self.assertEqual(rules2["min_references"], 20)

    def test_structure_finds_missing_statements(self):
        doc = load_document(SAMPLE_TXT)
        from papercheck.checks.structure import run as structure_run

        ctx = CheckContext(rules=get_rules("elsevier"))
        findings = structure_run(doc, ctx)
        titles = " | ".join(f.title for f in findings)
        self.assertIn("Missing required statement(s)", titles)
        self.assertTrue(any("Keywords" in f.title for f in findings))

    def test_citations_detect_uncited_references(self):
        doc = load_document(SAMPLE_TXT)
        from papercheck.checks.citations import run as citations_run

        ctx = CheckContext(rules=get_rules("generic"))
        findings = citations_run(doc, ctx)
        self.assertTrue(any("never cited" in f.title.lower() for f in findings))

    def test_forensics_detect_confusables_and_zero_width(self):
        from papercheck.ingestion import Document
        from papercheck.checks.forensics import run as forensics_run

        nasty = "The data\u200b set contains Cyrillic \u0430 instead of a."
        doc = Document(path="x.txt", name="x.txt", file_type="txt", text=nasty, paragraphs=[nasty])
        findings = forensics_run(doc, CheckContext(rules=get_rules("generic")))
        titles = " | ".join(f.title for f in findings)
        self.assertIn("Invisible", titles)
        self.assertIn("Lookalike", titles)

    def test_claims_detect_overstated_conclusion(self):
        from papercheck.ingestion import Document, Section
        from papercheck.checks.claims import run as claims_run

        text = "Intro text. " * 60
        conclusion = "This proves our method is always better and guarantees perfect results in all cases."
        doc = Document(
            path="c.txt", name="c.txt", file_type="txt", text=text + "\nConclusion\n" + conclusion,
            paragraphs=[text, "Conclusion", conclusion],
            sections=[Section(heading="Conclusion", level=1, body=conclusion, start_index=len(text))],
        )
        findings = claims_run(doc, CheckContext(rules=get_rules("generic")))
        self.assertTrue(any("Overstated" in f.title for f in findings))

    def test_policy_requires_disclosure(self):
        # Test that AI writing tool mentions trigger disclosure requirement
        from papercheck.checks.policy import run as policy_run
        doc = Document(
            path="test.txt", name="test.txt", file_type="text",
            text="This paper was assisted by ChatGPT for language polishing. " * 20,
            sections=[Section(heading="Abstract", level=1,
                body="This paper was assisted by ChatGPT for language polishing. " * 20, start_index=0)],
            paragraphs=["This paper was assisted by ChatGPT for language polishing. " * 20],
        )
        ctx = CheckContext(rules=get_rules("elsevier"))
        findings = policy_run(doc, ctx)
        self.assertTrue(any("AI-use disclosure" in f.title or "AI disclosure" in f.title for f in findings))


class TestReport(unittest.TestCase):
    def test_renderers(self):
        report = RiskReport(document_name="x.docx", venue="generic")
        report.add(Finding(category="T", severity=Severity.HIGH, title="H",
                           detail="d", evidence="e", action="a", confidence=0.8))
        self.assertIn("H", render_console(report))
        self.assertIn("| H |", render_markdown(report))
        self.assertIn("<table>", render_html(report))
        self.assertLessEqual(report.readiness_score, 100)


if __name__ == "__main__":
    unittest.main()
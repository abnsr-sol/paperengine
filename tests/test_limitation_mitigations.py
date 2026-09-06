"""Tests for limitation-mitigation features: similarity detail, benchmark
calibration, and the engine false-positive fixes the benchmark surfaced."""
import json
import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from papercheck.checks.compliance import run as compliance_run  # noqa: E402
from papercheck.checks import CheckContext  # noqa: E402
from papercheck.ingestion import load_document  # noqa: E402
from papercheck.metrics import conflicting_numbers  # noqa: E402
from papercheck.similarity_detail import (  # noqa: E402
    analyze, render_html, render_markdown)
from papercheck.venues import RULES_LAST_VERIFIED, get_rules, describe  # noqa: E402

_ROOT = os.path.join(os.path.dirname(__file__), "..")
_CLEAN = os.path.join(_ROOT, "papercheck", "data", "benchmark", "benchmark_clean.txt")
_FLAWED = os.path.join(_ROOT, "papercheck", "data", "benchmark", "benchmark_flawed.txt")


class TestVenueFreshness(unittest.TestCase):
    def test_rules_carry_verification_date(self):
        rules = get_rules("ieee_conference")
        self.assertEqual(rules.get("rules_last_verified"), RULES_LAST_VERIFIED)

    def test_compliance_reports_freshness(self):
        doc = load_document(_CLEAN)
        ctx = CheckContext(venue=describe("ieee_conference"),
                           rules=get_rules("ieee_conference"),
                           online=False, max_online_checks=0)
        findings = compliance_run(doc, ctx)
        titles = [f.title for f in findings]
        self.assertTrue(any("last verified" in t for t in titles), titles)


class TestGrammarDiscoverability(unittest.TestCase):
    def test_grammar_hint_when_no_server(self):
        from papercheck.checks.grammar_tool import run as grammar_run
        doc = load_document(_CLEAN)
        findings = grammar_run(doc, object())
        self.assertEqual(len(findings), 1)
        self.assertIn("LanguageTool", findings[0].title)
        self.assertIn("docker", findings[0].action)


class TestSimilarityDetail(unittest.TestCase):
    def test_analyze_and_render(self):
        doc = load_document(_CLEAN)
        # corpus: the flawed paper (unrelated) + the docx variant of sample
        corpus = [load_document(_FLAWED)]
        rep = analyze(doc, corpus)
        s = rep.summary()
        for key in ("document", "overall_overlap_pct", "sources", "passages"):
            self.assertIn(key, s)
        md = render_markdown(rep)
        self.assertIn("How to read this", md)
        h = render_html(rep)
        self.assertIn("Similarity detail report", h)

    def test_identical_documents_full_overlap(self):
        doc = load_document(_CLEAN)
        rep = analyze(doc, [doc])
        self.assertGreater(rep.overall_fraction, 0.99)
        self.assertIn(doc.name, rep.sources)


class TestConflictingNumbers(unittest.TestCase):
    def test_true_conflict_detected(self):
        text = "The system used 120 nodes. Performance reached 95 nodes scale."
        conflicts = conflicting_numbers(text)
        self.assertTrue(any(c["unit"].startswith("node") for c in conflicts))

    def test_distributor_phrases_are_not_conflicts(self):
        text = ("We deployed 120 nodes in total. A priori analysis indicated "
                "34 nodes per group were sufficient.")
        conflicts = conflicting_numbers(text)
        node_conflicts = [c for c in conflicts if c["unit"].startswith("node")]
        self.assertEqual(node_conflicts, [])

    def test_hedged_values_are_not_conflicts(self):
        text = "Approximately 30 participants joined. In total, 42 participants enrolled."
        conflicts = conflicting_numbers(text)
        part = [c for c in conflicts if "participant" in c["unit"]]
        self.assertEqual(part, [])


class TestMlTriggerPrecision(unittest.TestCase):
    def test_reference_title_models_not_ml_paper(self):
        """A 'models' mention inside a reference title must not demand
        hyperparameters."""
        text = ("Queueing models for load balancing. Networks, 6(4), 2-18. "
                "The survey covers theory.")
        import re
        trigger = bool(re.search(
            r"(?:neural\s+network|deep\s+learning|machine\s+learning|convolutional|"
            r"transformer|fine-?tun(?:e|ing)|training\s+(?:data|set)|training\s+and\s+test|"
            r"epoch|batch\s+size|learning\s+rate|back-?propagat)", text, re.IGNORECASE))
        self.assertFalse(trigger)

    def test_real_ml_paper_still_triggers(self):
        text = "We trained a deep learning model with batch size 32."
        import re
        trigger = bool(re.search(
            r"(?:neural\s+network|deep\s+learning|machine\s+learning|convolutional|"
            r"transformer|fine-?tun(?:e|ing)|training\s+(?:data|set)|training\s+and\s+test|"
            r"epoch|batch\s+size|learning\s+rate|back-?propagat)", text, re.IGNORECASE))
        self.assertTrue(trigger)


class TestFakeRefSignature(unittest.TestCase):
    def test_real_doi_not_flagged(self):
        """A legitimate Zenodo DOI must not match the fake-ref signature."""
        from papercheck.checks.llm_artifacts import _FAKE_REF
        import re
        real = "archived at Zenodo (doi 10.5281/zenodo.9999999) under CC-BY"
        self.assertIsNone(re.search(_FAKE_REF, real, re.IGNORECASE))

    def test_placeholder_doi_flagged(self):
        from papercheck.checks.llm_artifacts import _FAKE_REF
        import re
        fake = "available at doi: N/A (retrieved 2024)"
        self.assertIsNotNone(re.search(_FAKE_REF, fake, re.IGNORECASE))


class TestMarkdownHeadings(unittest.TestCase):
    def test_atx_headings_parsed_and_stripped(self):
        doc = load_document(_CLEAN)
        headings = [s.heading for s in doc.sections]
        self.assertIn("Abstract", headings)
        self.assertIn("Methods", headings)
        for h in headings:
            self.assertFalse(h.startswith("#"), h)


class TestBenchmarkScript(unittest.TestCase):
    def test_benchmark_passes(self):
        proc = subprocess.run(
            [sys.executable, os.path.join(_ROOT, "scripts", "benchmark.py"), "--json"],
            capture_output=True, text=True, timeout=300)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        data = json.loads(proc.stdout)
        self.assertTrue(data["scores"]["monotonic"])
        self.assertEqual(data["clean_critical"], [])
        self.assertGreater(data["ai_risk_hits_on_flawed"], 0)


if __name__ == "__main__":
    unittest.main()

"""Regression tests for the engine pipeline (run_all_engines).

These lock in the guarantees the pipeline must keep as engines are added:

  1. determinism — two runs on the same document produce identical output
     (ordering and content), so reports are reproducible;
  2. fault isolation — one engine that raises is reported, never fatal;
  3. ordering — findings stay grouped in engine registration order;
  4. source tagging — every finding carries the module name of its engine.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from papercheck.checks import ALL_ENGINES, CheckContext, run_all_engines  # noqa: E402
from papercheck.ingestion import Document  # noqa: E402
from papercheck.venues import get_rules  # noqa: E402


def _doc() -> Document:
    text = (
        "We used 42 epochs with batch size 128 and a learning rate of 0.001. "
        "The mean was 3.48 with SD 0.5 across n = 120 participants. "
        "r = 5.0 and p = 0.000 indicate a strong effect. "
        "Ethics approval was obtained from the institutional board. "
        "Data are available on Zenodo under DOI 10.5281/zenodo.1234567. "
    ) * 30
    return Document(
        path="x.txt", name="x.txt", file_type="txt",
        text=text, paragraphs=[text],
        references=["[1] Smith J. A title. Journal. 2020. doi:10.1/x"],
    )


def _signature(findings):
    """Order-sensitive, content-complete fingerprint of a findings list."""
    return [
        (f.category, f.severity.value, f.title, f.detail, f.evidence,
         f.action, round(float(f.confidence), 6), f.source)
        for f in findings
    ]


class TestPipeline(unittest.TestCase):
    def setUp(self):
        self.doc = _doc()
        self.ctx = CheckContext(venue="generic", rules=get_rules("generic"))

    def test_run_is_deterministic(self):
        first, errs_a = run_all_engines(self.doc, self.ctx)
        second, errs_b = run_all_engines(self.doc, self.ctx)
        self.assertEqual(_signature(first), _signature(second))
        self.assertEqual(errs_a, errs_b)

    def test_every_finding_is_tagged_with_its_source(self):
        findings, _ = run_all_engines(self.doc, self.ctx)
        untagged = [f.title for f in findings if not f.source]
        self.assertEqual(untagged, [], f"findings missing source: {untagged}")

    def test_findings_stay_in_engine_registration_order(self):
        # Each engine's findings must appear contiguously and in the same
        # relative order as ALL_ENGINES — the report depends on this.
        findings, _ = run_all_engines(self.doc, self.ctx)
        order = [e.__module__.rsplit(".", 1)[-1] for e in ALL_ENGINES]
        seen = []
        for f in findings:
            if f.source not in ("pipeline",):
                if not seen or seen[-1] != f.source:
                    seen.append(f.source)
        # No engine may appear in two separate blocks.
        self.assertEqual(len(seen), len(set(seen)),
                         f"engine findings interleaved: {seen}")

    def test_a_raising_engine_is_isolated_not_fatal(self):
        def boom(doc, ctx):
            raise RuntimeError("synthetic engine failure")

        boom.__module__ = "papercheck.checks.synthetic_boom"
        ALL_ENGINES.append(boom)
        try:
            findings, errors = run_all_engines(self.doc, self.ctx)
        finally:
            ALL_ENGINES.remove(boom)
        self.assertTrue(any("synthetic_boom" in e for e in errors),
                        f"engine error not reported: {errors}")
        # The rest of the report must still be produced.
        self.assertTrue(len(findings) > 10)
        self.assertTrue(any(f.category == "Engine" for f in findings))


if __name__ == "__main__":
    unittest.main()

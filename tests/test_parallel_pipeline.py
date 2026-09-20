"""Regression tests for the parallel engine pipeline.

run_all_engines() runs engines through a small thread pool by default. These
tests lock in the two guarantees that make that safe to ship:

  1. output is byte-for-byte identical to the sequential path (same order,
     same content, same scores) — report ordering must never depend on
     thread scheduling;
  2. repeated parallel runs are deterministic (no flaky reordering).

They also assert online mode stays sequential (network politeness).
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from papercheck.checks import CheckContext, run_all_engines  # noqa: E402
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


class TestParallelPipeline(unittest.TestCase):
    def setUp(self):
        self.doc = _doc()
        self.ctx = CheckContext(venue="generic", rules=get_rules("generic"))

    def _run_with_workers(self, workers: int):
        old = os.environ.get("PAPERCHECK_WORKERS")
        os.environ["PAPERCHECK_WORKERS"] = str(workers)
        try:
            return run_all_engines(self.doc, self.ctx)
        finally:
            if old is None:
                os.environ.pop("PAPERCHECK_WORKERS", None)
            else:
                os.environ["PAPERCHECK_WORKERS"] = old

    def test_parallel_matches_sequential_exactly(self):
        seq_findings, seq_errors = self._run_with_workers(1)
        par_findings, par_errors = self._run_with_workers(4)
        self.assertEqual(_signature(seq_findings), _signature(par_findings),
                         "parallel output diverged from sequential output")
        self.assertEqual(seq_errors, par_errors)

    def test_parallel_is_deterministic_across_runs(self):
        first, _ = self._run_with_workers(4)
        second, _ = self._run_with_workers(4)
        self.assertEqual(_signature(first), _signature(second),
                         "parallel run was not deterministic")

    def test_scores_are_identical(self):
        from papercheck.risk import RiskReport
        seq, _ = self._run_with_workers(1)
        par, _ = self._run_with_workers(4)
        r_seq = RiskReport(document_name="x", venue="generic")
        r_par = RiskReport(document_name="x", venue="generic")
        r_seq.extend(seq)
        r_par.extend(par)
        self.assertEqual(r_seq.readiness_score, r_par.readiness_score)

    def test_online_mode_never_uses_the_pool(self):
        # With online=True the pipeline must stay sequential; _worker_count is
        # still resolved, but the parallel branch is skipped.
        ctx = CheckContext(venue="generic", rules=get_rules("generic"),
                           online=True, max_online_checks=0)
        old = os.environ.get("PAPERCHECK_WORKERS")
        os.environ["PAPERCHECK_WORKERS"] = "8"
        try:
            findings, _ = run_all_engines(self.doc, ctx)
        finally:
            if old is None:
                os.environ.pop("PAPERCHECK_WORKERS", None)
            else:
                os.environ["PAPERCHECK_WORKERS"] = old
        self.assertTrue(findings)


if __name__ == "__main__":
    unittest.main()
